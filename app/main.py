"""FastAPI application for RhôneRisk Cyber Insurance Policy Analyzer.

All analysis endpoints are protected by local JWT authentication.
Each user has an isolated environment — they only see their own analyses.
Analysis metadata is persisted to Supabase (or SQLite fallback) via app.database.
"""

import asyncio
import logging
import os
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import StreamingResponse

from app.analysis.engine import AnalysisEngine
from app.auth import (
    AuthUser,
    get_current_user,
    user_registry,
    create_user,
    authenticate_user,
    generate_tokens,
    refresh_access_token,
)
from app.config import get_settings
from app.models.requests import ClientInfo
from app.models.responses import AnalysisSummaryResponse, AnalysisStatusResponse, HealthResponse
from app.models.scoring import PolicyAnalysis
from app.monitoring import registry

logger = logging.getLogger(__name__)


def _validate_knowledge_base() -> bool:
    settings = get_settings()
    required = [
        settings.knowledge_dir / "system_prompt.md",
        settings.knowledge_dir / "scoring_methodology.yaml",
        settings.knowledge_dir / "coverage_definitions.yaml",
        settings.knowledge_dir / "red_flags.yaml",
        settings.knowledge_dir / "report_sections.yaml",
    ]
    return all(f.exists() for f in required)


def _r2_configured() -> bool:
    settings = get_settings()
    return bool(settings.r2_account_id and settings.r2_access_key_id and settings.r2_secret_access_key)


def _get_r2_client():
    from app.storage.r2 import R2StorageClient
    return R2StorageClient()


def _persist_analysis_update(analysis_id: str, **fields):
    """Persist analysis metadata updates to the database (best-effort)."""
    try:
        from app.database import db
        db.update_analysis(analysis_id, **fields)
    except Exception as e:
        logger.warning("[%s] Failed to persist analysis update: %s", analysis_id, e)


# ---------------------------------------------------------------------------
# Background analysis task (per-user)
# ---------------------------------------------------------------------------

def _run_analysis_background(
    analysis_id: str,
    user_id: str,
    pdf_path: Path,
    client_info: ClientInfo,
    pdf_dir: Path,
) -> None:
    settings = get_settings()
    record = registry.get(analysis_id)
    store = user_registry.get_store(user_id)

    def progress_callback(status: str, progress: int) -> None:
        store.statuses[analysis_id] = AnalysisStatusResponse(
            analysis_id=analysis_id,
            status=status,
            progress=progress,
        )
        _persist_analysis_update(analysis_id, status=status)

    try:
        progress_callback("extracting", 10)

        engine = AnalysisEngine()
        output_dir = settings.temp_dir / "reports" / user_id
        output_dir.mkdir(parents=True, exist_ok=True)

        analysis = engine.analyze_policy(
            pdf_path=pdf_path,
            client_info=client_info,
            output_dir=output_dir,
            progress_callback=progress_callback,
            record=record,
        )

        store.analyses[analysis_id] = analysis

        report_pdf_path: Path | None = None
        if output_dir.exists():
            pdfs = sorted(output_dir.glob("RhoneRisk_Analysis_*"), key=lambda p: p.stat().st_mtime)
            if pdfs:
                report_pdf_path = pdfs[-1]

        has_report = False
        report_r2_key = None

        if report_pdf_path and report_pdf_path.exists() and _r2_configured():
            try:
                r2 = _get_r2_client()
                report_r2_key = f"reports/{user_id}/{analysis_id}/{report_pdf_path.name}"
                r2.upload_file(report_r2_key, report_pdf_path.read_bytes())
                store.report_r2_paths[analysis_id] = report_r2_key
                has_report = True
                logger.info("[%s] Report uploaded to R2: %s", analysis_id, report_r2_key)
            except Exception as e:
                logger.warning("[%s] R2 upload failed, keeping local copy: %s", analysis_id, e)
                store.report_paths[analysis_id] = report_pdf_path
                has_report = True
        elif report_pdf_path and report_pdf_path.exists():
            store.report_paths[analysis_id] = report_pdf_path
            has_report = True

        store.statuses[analysis_id] = AnalysisStatusResponse(
            analysis_id=analysis_id,
            status="completed",
            progress=100,
        )

        # Persist completed analysis metadata to database
        completed_at = datetime.now(timezone.utc).isoformat()
        _persist_analysis_update(
            analysis_id,
            status="completed",
            overall_score=analysis.overall_score,
            overall_rating=analysis.overall_rating,
            binding_recommendation=analysis.binding_recommendation,
            red_flag_count=analysis.red_flag_count,
            critical_gap_count=len(analysis.critical_gaps) if analysis.critical_gaps else 0,
            has_report=has_report,
            report_r2_key=report_r2_key,
            total_duration_seconds=record.total_duration_seconds if record else 0,
            scoring_input_tokens=record.scoring_input_tokens if record else 0,
            scoring_output_tokens=record.scoring_output_tokens if record else 0,
            narrative_input_tokens=record.narrative_input_tokens if record else 0,
            narrative_output_tokens=record.narrative_output_tokens if record else 0,
            page_count=record.page_count if record else 0,
            completed_at=completed_at,
        )

    except Exception as e:
        logger.exception("[%s] Analysis failed", analysis_id)
        store.statuses[analysis_id] = AnalysisStatusResponse(
            analysis_id=analysis_id,
            status="failed",
            progress=0,
            error=str(e),
        )
        if record:
            record.mark_failed(str(e))
        _persist_analysis_update(
            analysis_id,
            status="failed",
            error=str(e),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

    finally:
        shutil.rmtree(pdf_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings.temp_dir.mkdir(parents=True, exist_ok=True)

    if not _validate_knowledge_base():
        logger.error("Knowledge base files missing! Check app/knowledge/ directory.")
    else:
        logger.info("Knowledge base validated successfully.")

    if _r2_configured():
        logger.info("R2 storage configured (bucket: %s)", settings.r2_bucket_name)
    else:
        logger.warning("R2 storage not configured — reports will be stored locally only.")

    # Log which database backend is active
    from app.database import db
    backend_name = type(db).__name__
    logger.info("Database backend: %s", backend_name)
    logger.info("Local JWT authentication enabled.")
    logger.info("RhôneRisk Policy Analyzer started. Model: %s", settings.claude_model)
    yield
    logger.info("RhôneRisk Policy Analyzer shutting down.")


app = FastAPI(
    title="RhôneRisk Cyber Insurance Policy Analyzer",
    description="AI-powered cyber insurance policy analysis with proprietary 21-section framework and 4-tier maturity scoring.",
    version="0.4.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Static files & frontend
# ---------------------------------------------------------------------------
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Public endpoints (no auth required)
# ---------------------------------------------------------------------------

@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        status="ok",
        version="0.4.0",
        knowledge_base_loaded=_validate_knowledge_base(),
    )


@app.get("/api/v1/auth/config")
async def auth_config():
    """Return auth configuration for the frontend client."""
    return JSONResponse(content={
        "auth_type": "local",
        "message": "Local JWT authentication is enabled.",
    })


@app.post("/api/v1/auth/register")
async def auth_register(request: Request):
    """Register a new user with local auth."""
    body = await request.json()
    email = body.get("email", "").strip()
    password = body.get("password", "")
    display_name = body.get("display_name", "")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required.")

    # create_user validates email format and password length, raises HTTPException on error
    user = create_user(email=email, password=password, display_name=display_name)

    # Generate tokens immediately (no email confirmation needed)
    tokens = generate_tokens(user)

    return JSONResponse(content={
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "expires_in": tokens["expires_in"],
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
        },
    })


@app.post("/api/v1/auth/login")
async def auth_login(request: Request):
    """Log in a user with local auth."""
    body = await request.json()
    email = body.get("email", "").strip()
    password = body.get("password", "")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password are required.")

    # authenticate_user validates credentials, raises HTTPException on failure
    user = authenticate_user(email=email, password=password)

    # Generate tokens
    tokens = generate_tokens(user)

    return JSONResponse(content={
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "expires_in": tokens["expires_in"],
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "created_at": user.created_at,
        },
    })


@app.post("/api/v1/auth/refresh")
async def auth_refresh(request: Request):
    """Refresh an access token using a refresh token."""
    body = await request.json()
    refresh_token = body.get("refresh_token", "")

    if not refresh_token:
        raise HTTPException(status_code=400, detail="Refresh token is required.")

    # refresh_access_token validates the refresh token, raises HTTPException on failure
    tokens = refresh_access_token(refresh_token)

    return JSONResponse(content={
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "expires_in": tokens["expires_in"],
    })


@app.get("/api/v1/auth/me")
async def auth_me(user: AuthUser = Depends(get_current_user)):
    """Return the currently authenticated user's profile."""
    return JSONResponse(content={
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "created_at": user.created_at,
    })


# ---------------------------------------------------------------------------
# Protected endpoints (auth required, per-user isolation)
# ---------------------------------------------------------------------------

@app.post("/api/v1/analyze", status_code=202)
async def analyze_policy(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(description="Cyber insurance policy PDF")],
    client_name: Annotated[str, Form()] = "",
    industry: Annotated[str, Form()] = "",
    annual_revenue: Annotated[str, Form()] = "",
    employee_count: Annotated[str, Form()] = "",
    is_msp: Annotated[bool, Form()] = False,
    notes: Annotated[str, Form()] = "",
    user: AuthUser = Depends(get_current_user),
):
    settings = get_settings()
    store = user_registry.get_store(user.id)

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {settings.max_upload_size_mb}MB.",
        )

    analysis_id = uuid.uuid4().hex[:12]

    pdf_dir = settings.temp_dir / "uploads" / user.id / analysis_id
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / file.filename
    pdf_path.write_bytes(content)

    if _r2_configured():
        try:
            r2 = _get_r2_client()
            policy_r2_key = f"policies/{user.id}/{analysis_id}/{file.filename}"
            r2.upload_file(policy_r2_key, content)
            store.policy_r2_paths[analysis_id] = policy_r2_key
        except Exception as e:
            logger.warning("[%s] Failed to upload policy PDF to R2: %s", analysis_id, e)

    client_info = ClientInfo(
        client_name=client_name,
        industry=industry,
        annual_revenue=annual_revenue,
        employee_count=employee_count,
        is_msp=is_msp,
        notes=notes,
    )

    # Create monitoring record
    record = registry.create(
        analysis_id=analysis_id,
        client_name=client_name or "Unknown",
        filename=file.filename,
        file_size_bytes=len(content),
    )
    record.add_log("INFO", "upload", f"Received {file.filename} ({len(content) / 1024:.0f} KB) from {user.email}")

    # Register ownership and track start time
    user_registry.register_analysis(user.id, analysis_id)
    store.start_times[analysis_id] = time.time()

    store.statuses[analysis_id] = AnalysisStatusResponse(
        analysis_id=analysis_id,
        status="pending",
        progress=0,
    )

    # Persist analysis record to database
    try:
        from app.database import db
        db.create_analysis(
            analysis_id=analysis_id,
            user_id=user.id,
            client_name=client_name or "Unknown",
            filename=file.filename,
            file_size_bytes=len(content),
        )
    except Exception as e:
        logger.warning("[%s] Failed to persist analysis to database: %s", analysis_id, e)

    background_tasks.add_task(
        _run_analysis_background,
        analysis_id=analysis_id,
        user_id=user.id,
        pdf_path=pdf_path,
        client_info=client_info,
        pdf_dir=pdf_dir,
    )

    return JSONResponse(
        status_code=202,
        content={
            "analysis_id": analysis_id,
            "status": "pending",
        },
    )


@app.get("/api/v1/analyze/{analysis_id}/status", response_model=AnalysisStatusResponse)
async def get_analysis_status(analysis_id: str, user: AuthUser = Depends(get_current_user)):
    store = user_registry.get_store(user.id)

    if not user_registry.verify_ownership(user.id, analysis_id):
        raise HTTPException(status_code=404, detail="Analysis not found.")

    if analysis_id not in store.statuses:
        raise HTTPException(status_code=404, detail="Analysis not found.")

    status = store.statuses[analysis_id]

    # Calculate elapsed time
    elapsed_seconds = 0.0
    if analysis_id in store.start_times:
        if status.status in ("completed", "failed"):
            record = registry.get(analysis_id)
            elapsed_seconds = record.total_duration_seconds if record else 0.0
        else:
            elapsed_seconds = time.time() - store.start_times[analysis_id]

    if status.status == "completed" and analysis_id in store.analyses:
        analysis = store.analyses[analysis_id]
        report_url = f"/api/v1/analyze/{analysis_id}/report" if (
            analysis_id in store.report_r2_paths or analysis_id in store.report_paths
        ) else None

        return JSONResponse(content={
            "analysis_id": analysis_id,
            "status": "completed",
            "progress": 100,
            "overall_score": analysis.overall_score,
            "overall_rating": analysis.overall_rating,
            "binding_recommendation": analysis.binding_recommendation,
            "report_url": report_url,
            "elapsed_seconds": round(elapsed_seconds, 1),
        })

    return JSONResponse(content={
        "analysis_id": status.analysis_id,
        "status": status.status,
        "progress": status.progress,
        "error": status.error,
        "elapsed_seconds": round(elapsed_seconds, 1),
    })


@app.get("/api/v1/analyze/{analysis_id}")
async def get_analysis(analysis_id: str, user: AuthUser = Depends(get_current_user)):
    store = user_registry.get_store(user.id)

    if not user_registry.verify_ownership(user.id, analysis_id):
        raise HTTPException(status_code=404, detail="Analysis not found.")

    if analysis_id not in store.analyses:
        if analysis_id in store.statuses:
            status = store.statuses[analysis_id]
            if status.status in ("pending", "extracting", "parsing", "scoring",
                                 "post_processing", "generating_narrative", "generating_report"):
                return JSONResponse(
                    status_code=202,
                    content={
                        "analysis_id": analysis_id,
                        "status": status.status,
                        "progress": status.progress,
                        "message": "Analysis is still in progress. Poll /status for updates.",
                    },
                )
            elif status.status == "failed":
                raise HTTPException(status_code=500, detail=f"Analysis failed: {status.error}")
        raise HTTPException(status_code=404, detail="Analysis not found.")

    analysis = store.analyses[analysis_id]
    report_url = f"/api/v1/analyze/{analysis_id}/report" if (
        analysis_id in store.report_r2_paths or analysis_id in store.report_paths
    ) else None

    return AnalysisSummaryResponse(
        analysis_id=analysis.analysis_id,
        status=analysis.status,
        policy_metadata=analysis.policy_metadata,
        overall_score=analysis.overall_score,
        overall_rating=analysis.overall_rating,
        binding_recommendation=analysis.binding_recommendation,
        binding_rationale=analysis.binding_rationale,
        coverage_scores=analysis.coverage_scores,
        red_flag_count=analysis.red_flag_count,
        critical_gaps=analysis.critical_gaps,
        category_summaries=analysis.category_summaries or [],
        strategic_recommendations=analysis.strategic_recommendations or [],
        report_pdf_url=report_url,
    )


@app.get("/api/v1/analyze/{analysis_id}/report")
async def download_report(analysis_id: str, user: AuthUser = Depends(get_current_user)):
    store = user_registry.get_store(user.id)

    if not user_registry.verify_ownership(user.id, analysis_id):
        raise HTTPException(status_code=404, detail="Analysis not found.")

    if analysis_id in store.report_r2_paths and _r2_configured():
        try:
            r2 = _get_r2_client()
            signed_url = r2.get_signed_url(store.report_r2_paths[analysis_id], expires_in=3600)
            return RedirectResponse(url=signed_url, status_code=302)
        except Exception as e:
            logger.warning("[%s] Failed to generate R2 signed URL: %s", analysis_id, e)

    if analysis_id in store.report_paths:
        report_path = store.report_paths[analysis_id]
        if report_path.exists():
            return FileResponse(
                path=str(report_path),
                media_type="application/pdf",
                filename=report_path.name,
            )

    if analysis_id in store.statuses:
        status = store.statuses[analysis_id]
        if status.status not in ("completed", "failed"):
            raise HTTPException(
                status_code=202,
                detail="Analysis is still in progress. Report not yet available.",
            )
        if status.status == "failed":
            raise HTTPException(status_code=500, detail=f"Analysis failed: {status.error}")

    raise HTTPException(status_code=404, detail="Report not found.")


# ---------------------------------------------------------------------------
# Monitoring endpoints (per-user)
# ---------------------------------------------------------------------------

@app.get("/api/v1/analyses")
async def list_analyses(user: AuthUser = Depends(get_current_user)):
    """Return all analysis records for the authenticated user.

    Merges in-memory monitoring data with persisted database records.
    """
    store = user_registry.get_store(user.id)

    # Get in-memory records from the monitoring registry
    user_analyses = []
    seen_ids = set()
    for record_dict in registry.list_all():
        aid = record_dict.get("analysis_id", "")
        if user_registry.verify_ownership(user.id, aid):
            user_analyses.append(record_dict)
            seen_ids.add(aid)

    # Also fetch persisted records from the database (for analyses from previous sessions)
    try:
        from app.database import db
        db_analyses = db.list_user_analyses(user.id, limit=50)
        for row in db_analyses:
            aid = row.get("id", "")
            if aid not in seen_ids:
                # Convert DB row to monitoring-compatible format
                user_analyses.append({
                    "analysis_id": aid,
                    "client_name": row.get("client_name", ""),
                    "filename": row.get("filename", ""),
                    "status": row.get("status", "unknown"),
                    "start_time": row.get("created_at"),
                    "total_duration_seconds": row.get("total_duration_seconds", 0),
                    "overall_score": row.get("overall_score"),
                    "overall_rating": row.get("overall_rating"),
                    "binding_recommendation": row.get("binding_recommendation"),
                    "red_flag_count": row.get("red_flag_count", 0),
                    "has_report": row.get("has_report", False),
                })
                seen_ids.add(aid)
    except Exception as e:
        logger.warning("Failed to fetch persisted analyses: %s", e)

    return JSONResponse(content={"analyses": user_analyses})


@app.get("/api/v1/analyze/{analysis_id}/logs")
async def stream_logs(analysis_id: str, user: AuthUser = Depends(get_current_user)):
    """Server-Sent Events endpoint for real-time log streaming (per-user)."""
    if not user_registry.verify_ownership(user.id, analysis_id):
        raise HTTPException(status_code=404, detail="Analysis not found.")

    record = registry.get(analysis_id)
    if not record:
        raise HTTPException(status_code=404, detail="Analysis not found.")

    async def event_generator():
        import json

        for entry in record.logs:
            yield entry.to_sse()

        if record.status in ("completed", "failed"):
            yield f"data: {json.dumps({'type': 'close', 'status': record.status})}\n\n"
            return

        queue = record.subscribe()
        try:
            while True:
                try:
                    entry = await asyncio.wait_for(queue.get(), timeout=30.0)
                    if entry is None:
                        yield f"data: {json.dumps({'type': 'close', 'status': record.status})}\n\n"
                        return
                    yield entry.to_sse()
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            record.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/v1/analyze/{analysis_id}/timing")
async def get_analysis_timing(analysis_id: str, user: AuthUser = Depends(get_current_user)):
    """Get detailed timing breakdown for a specific analysis (per-user)."""
    if not user_registry.verify_ownership(user.id, analysis_id):
        raise HTTPException(status_code=404, detail="Analysis not found.")

    record = registry.get(analysis_id)
    if not record:
        raise HTTPException(status_code=404, detail="Analysis not found.")
    return JSONResponse(content=record.to_dict())


# ---------------------------------------------------------------------------
# Dashboard endpoint (per-user)
# ---------------------------------------------------------------------------

@app.get("/api/v1/dashboard")
async def get_dashboard(user: AuthUser = Depends(get_current_user)):
    """Return personalized dashboard data for the authenticated user.

    Aggregates per-user stats (total/completed/failed analyses, average score)
    and returns the most recent analyses with scores, client names, and report links.
    Merges in-memory data with persisted database records.
    """
    store = user_registry.get_store(user.id)

    # Collect this user's analysis records — merge in-memory + database
    user_analyses = []
    seen_ids = set()

    # In-memory records from monitoring registry
    for record_dict in registry.list_all():
        aid = record_dict.get("analysis_id", "")
        if user_registry.verify_ownership(user.id, aid):
            entry = dict(record_dict)
            # Enrich with score data from in-memory store
            if aid in store.analyses:
                analysis_obj = store.analyses[aid]
                entry["overall_score"] = analysis_obj.overall_score
                entry["overall_rating"] = analysis_obj.overall_rating
                entry["binding_recommendation"] = analysis_obj.binding_recommendation
                entry["red_flag_count"] = analysis_obj.red_flag_count
            entry["has_report"] = (
                aid in store.report_paths or aid in store.report_r2_paths
            )
            user_analyses.append(entry)
            seen_ids.add(aid)

    # Persisted records from database (for analyses from previous sessions)
    try:
        from app.database import db
        db_analyses = db.list_user_analyses(user.id, limit=50)
        for row in db_analyses:
            aid = row.get("id", "")
            if aid not in seen_ids:
                user_analyses.append({
                    "analysis_id": aid,
                    "client_name": row.get("client_name", ""),
                    "filename": row.get("filename", ""),
                    "status": row.get("status", "unknown"),
                    "start_time": row.get("created_at"),
                    "total_duration_seconds": row.get("total_duration_seconds", 0),
                    "overall_score": row.get("overall_score"),
                    "overall_rating": row.get("overall_rating"),
                    "binding_recommendation": row.get("binding_recommendation"),
                    "red_flag_count": row.get("red_flag_count", 0),
                    "has_report": row.get("has_report", False),
                })
                seen_ids.add(aid)
    except Exception as e:
        logger.warning("Failed to fetch persisted analyses for dashboard: %s", e)

    total = len(user_analyses)
    completed = [a for a in user_analyses if a.get("status") == "completed"]
    failed = [a for a in user_analyses if a.get("status") == "failed"]
    in_progress = total - len(completed) - len(failed)

    # Calculate average score
    scores = [a["overall_score"] for a in completed if a.get("overall_score") is not None]
    avg_score = round(sum(scores) / len(scores), 1) if scores else None

    # Calculate average duration
    durations = [a["total_duration_seconds"] for a in completed if a.get("total_duration_seconds", 0) > 0]
    avg_duration = round(sum(durations) / len(durations), 1) if durations else None

    # Build recent analyses list (up to 20, most recent first)
    recent = []
    for a in user_analyses[:20]:
        aid = a.get("analysis_id", a.get("id", ""))
        entry = {
            "analysis_id": aid,
            "client_name": a.get("client_name", ""),
            "filename": a.get("filename", ""),
            "status": a.get("status", "unknown"),
            "start_time": a.get("start_time"),
            "total_duration_seconds": a.get("total_duration_seconds", 0),
            "overall_score": a.get("overall_score"),
            "overall_rating": a.get("overall_rating"),
            "binding_recommendation": a.get("binding_recommendation"),
            "red_flag_count": a.get("red_flag_count"),
            "has_report": a.get("has_report", False),
        }
        recent.append(entry)

    # Member since date — look up from database
    member_since = None
    try:
        from app.auth import get_user_by_id
        db_user = get_user_by_id(user.id)
        if db_user and db_user.created_at:
            created_str = db_user.created_at
            # Handle both timestamp (float) and ISO string formats
            try:
                created_ts = float(created_str)
                member_since = datetime.fromtimestamp(created_ts).strftime("%B %d, %Y")
            except (ValueError, TypeError):
                # ISO format from Supabase
                try:
                    dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    member_since = dt.strftime("%B %d, %Y")
                except (ValueError, TypeError):
                    member_since = created_str
    except Exception:
        pass

    return JSONResponse(content={
        "user": {
            "id": user.id,
            "email": user.email,
            "display_name": user.display_name,
            "member_since": member_since,
        },
        "stats": {
            "total_analyses": total,
            "completed": len(completed),
            "failed": len(failed),
            "in_progress": in_progress,
            "average_score": avg_score,
            "average_duration_seconds": avg_duration,
        },
        "recent_analyses": recent,
    })


# ---------------------------------------------------------------------------
# Frontend catch-all (must be last)
# ---------------------------------------------------------------------------

@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    return FileResponse(str(_STATIC_DIR / "index.html"), media_type="text/html")

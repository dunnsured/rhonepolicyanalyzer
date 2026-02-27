"""FastAPI application for RhôneRisk Cyber Insurance Policy Analyzer."""

import logging
import shutil
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse

from app.analysis.engine import AnalysisEngine
from app.config import get_settings
from app.models.requests import ClientInfo
from app.models.responses import AnalysisSummaryResponse, AnalysisStatusResponse, HealthResponse
from app.models.scoring import PolicyAnalysis

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------
# Analysis results keyed by analysis_id
_analyses: dict[str, PolicyAnalysis] = {}

# Status tracking keyed by analysis_id
_analysis_status: dict[str, AnalysisStatusResponse] = {}

# R2 bucket paths for generated report PDFs keyed by analysis_id
_report_r2_paths: dict[str, str] = {}

# R2 bucket paths for uploaded policy PDFs keyed by analysis_id
_policy_r2_paths: dict[str, str] = {}

# Fallback: local report paths (used when R2 is not configured)
_report_paths: dict[str, Path] = {}


def _validate_knowledge_base() -> bool:
    """Check that all knowledge base files exist."""
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
    """Check whether R2 credentials are set."""
    settings = get_settings()
    return bool(settings.r2_account_id and settings.r2_access_key_id and settings.r2_secret_access_key)


def _get_r2_client():
    """Lazily import and instantiate the R2 storage client."""
    from app.storage.r2 import R2StorageClient
    return R2StorageClient()


# ---------------------------------------------------------------------------
# Background analysis task
# ---------------------------------------------------------------------------

def _run_analysis_background(
    analysis_id: str,
    pdf_path: Path,
    client_info: ClientInfo,
    pdf_dir: Path,
) -> None:
    """Execute the analysis pipeline in a background thread.

    Updates the in-memory status dict at each pipeline stage and
    uploads the final report PDF to R2 on completion.
    """
    settings = get_settings()

    def progress_callback(status: str, progress: int) -> None:
        """Update the in-memory status tracker."""
        _analysis_status[analysis_id] = AnalysisStatusResponse(
            analysis_id=analysis_id,
            status=status,
            progress=progress,
        )

    try:
        # Set initial status
        progress_callback("extracting", 10)

        engine = AnalysisEngine()
        output_dir = settings.temp_dir / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)

        analysis = engine.analyze_policy(
            pdf_path=pdf_path,
            client_info=client_info,
            output_dir=output_dir,
            progress_callback=progress_callback,
        )

        # Store analysis results
        _analyses[analysis_id] = analysis

        # Find the generated report PDF
        report_pdf_path: Path | None = None
        if output_dir.exists():
            pdfs = sorted(output_dir.glob("RhoneRisk_Analysis_*"), key=lambda p: p.stat().st_mtime)
            if pdfs:
                report_pdf_path = pdfs[-1]

        # Upload report PDF to R2 if configured
        if report_pdf_path and report_pdf_path.exists() and _r2_configured():
            try:
                r2 = _get_r2_client()
                report_r2_key = f"reports/{analysis_id}/{report_pdf_path.name}"
                r2.upload_file(report_r2_key, report_pdf_path.read_bytes())
                _report_r2_paths[analysis_id] = report_r2_key
                logger.info("[%s] Report uploaded to R2: %s", analysis_id, report_r2_key)
            except Exception as e:
                logger.warning("[%s] R2 upload failed, keeping local copy: %s", analysis_id, e)
                _report_paths[analysis_id] = report_pdf_path
        elif report_pdf_path and report_pdf_path.exists():
            _report_paths[analysis_id] = report_pdf_path

        # Final status: completed
        _analysis_status[analysis_id] = AnalysisStatusResponse(
            analysis_id=analysis_id,
            status="completed",
            progress=100,
        )

    except Exception as e:
        logger.exception("[%s] Analysis failed", analysis_id)
        _analysis_status[analysis_id] = AnalysisStatusResponse(
            analysis_id=analysis_id,
            status="failed",
            progress=0,
            error=str(e),
        )

    finally:
        # Clean up uploaded PDF directory
        shutil.rmtree(pdf_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Application lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    settings = get_settings()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Create temp directory
    settings.temp_dir.mkdir(parents=True, exist_ok=True)

    # Validate knowledge base
    if not _validate_knowledge_base():
        logger.error("Knowledge base files missing! Check app/knowledge/ directory.")
    else:
        logger.info("Knowledge base validated successfully.")

    # Log R2 configuration status
    if _r2_configured():
        logger.info("R2 storage configured (bucket: %s)", settings.r2_bucket_name)
    else:
        logger.warning("R2 storage not configured — reports will be stored locally only.")

    logger.info("RhôneRisk Policy Analyzer started. Model: %s", settings.claude_model)
    yield
    logger.info("RhôneRisk Policy Analyzer shutting down.")


app = FastAPI(
    title="RhôneRisk Cyber Insurance Policy Analyzer",
    description="AI-powered cyber insurance policy analysis with proprietary 21-section framework and 4-tier maturity scoring.",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        version="0.1.0",
        knowledge_base_loaded=_validate_knowledge_base(),
    )


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
):
    """Submit a cyber insurance policy PDF for analysis.

    Returns HTTP 202 immediately with an analysis_id. The analysis
    runs asynchronously in the background. Poll
    ``GET /api/v1/analyze/{id}/status`` for progress.
    """
    settings = get_settings()

    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted.")

    # Validate file size
    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {settings.max_upload_size_mb}MB.",
        )

    # Generate analysis ID
    analysis_id = uuid.uuid4().hex[:12]

    # Save PDF to local temp directory for the background task
    pdf_dir = settings.temp_dir / "uploads" / analysis_id
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / file.filename
    pdf_path.write_bytes(content)

    # Upload policy PDF to R2 if configured
    if _r2_configured():
        try:
            r2 = _get_r2_client()
            policy_r2_key = f"policies/{analysis_id}/{file.filename}"
            r2.upload_file(policy_r2_key, content)
            _policy_r2_paths[analysis_id] = policy_r2_key
        except Exception as e:
            logger.warning("[%s] Failed to upload policy PDF to R2: %s", analysis_id, e)

    # Build client info
    client_info = ClientInfo(
        client_name=client_name,
        industry=industry,
        annual_revenue=annual_revenue,
        employee_count=employee_count,
        is_msp=is_msp,
        notes=notes,
    )

    # Set initial status
    _analysis_status[analysis_id] = AnalysisStatusResponse(
        analysis_id=analysis_id,
        status="pending",
        progress=0,
    )

    # Schedule background analysis
    background_tasks.add_task(
        _run_analysis_background,
        analysis_id=analysis_id,
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
async def get_analysis_status(analysis_id: str):
    """Poll for analysis progress.

    Returns the current pipeline stage and progress percentage.
    When status is ``completed``, the report is ready for download.
    """
    if analysis_id not in _analysis_status:
        raise HTTPException(status_code=404, detail="Analysis not found.")

    status = _analysis_status[analysis_id]

    # If completed, include report URL and summary info
    if status.status == "completed" and analysis_id in _analyses:
        analysis = _analyses[analysis_id]
        report_url = f"/api/v1/analyze/{analysis_id}/report" if (
            analysis_id in _report_r2_paths or analysis_id in _report_paths
        ) else None

        return JSONResponse(content={
            "analysis_id": analysis_id,
            "status": "completed",
            "progress": 100,
            "overall_score": analysis.overall_score,
            "overall_rating": analysis.overall_rating,
            "binding_recommendation": analysis.binding_recommendation,
            "report_url": report_url,
        })

    return status


@app.get("/api/v1/analyze/{analysis_id}")
async def get_analysis(analysis_id: str):
    """Get full analysis results by ID."""
    if analysis_id not in _analyses:
        # Check if it's still in progress
        if analysis_id in _analysis_status:
            status = _analysis_status[analysis_id]
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

    analysis = _analyses[analysis_id]
    report_url = f"/api/v1/analyze/{analysis_id}/report" if (
        analysis_id in _report_r2_paths or analysis_id in _report_paths
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
        report_pdf_url=report_url,
    )


@app.get("/api/v1/analyze/{analysis_id}/report")
async def download_report(analysis_id: str):
    """Download the generated PDF report.

    If R2 is configured, returns a 302 redirect to a pre-signed R2 URL
    (valid for 1 hour). Otherwise, serves the file directly from local storage.
    """
    # Try R2 first
    if analysis_id in _report_r2_paths and _r2_configured():
        try:
            r2 = _get_r2_client()
            signed_url = r2.get_signed_url(_report_r2_paths[analysis_id], expires_in=3600)
            return RedirectResponse(url=signed_url, status_code=302)
        except Exception as e:
            logger.warning("[%s] Failed to generate R2 signed URL: %s", analysis_id, e)

    # Fallback to local file
    if analysis_id in _report_paths:
        from fastapi.responses import FileResponse
        report_path = _report_paths[analysis_id]
        if report_path.exists():
            return FileResponse(
                path=str(report_path),
                media_type="application/pdf",
                filename=report_path.name,
            )

    # Check if analysis is still running
    if analysis_id in _analysis_status:
        status = _analysis_status[analysis_id]
        if status.status not in ("completed", "failed"):
            raise HTTPException(
                status_code=202,
                detail="Analysis is still in progress. Report not yet available.",
            )
        if status.status == "failed":
            raise HTTPException(status_code=500, detail=f"Analysis failed: {status.error}")

    raise HTTPException(status_code=404, detail="Report not found.")

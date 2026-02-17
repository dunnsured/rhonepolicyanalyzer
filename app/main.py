"""FastAPI application for RhôneRisk Cyber Insurance Policy Analyzer."""

import logging
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from app.analysis.engine import AnalysisEngine
from app.config import get_settings
from app.models.requests import ClientInfo
from app.models.responses import AnalysisSummaryResponse, AnalysisStatusResponse, HealthResponse
from app.models.scoring import PolicyAnalysis

logger = logging.getLogger(__name__)

# In-memory store for analysis results (swap for Redis/DB in production)
_analyses: dict[str, PolicyAnalysis] = {}
_analysis_status: dict[str, AnalysisStatusResponse] = {}
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

    logger.info("RhôneRisk Policy Analyzer started. Model: %s", settings.claude_model)
    yield
    logger.info("RhôneRisk Policy Analyzer shutting down.")


app = FastAPI(
    title="RhôneRisk Cyber Insurance Policy Analyzer",
    description="AI-powered cyber insurance policy analysis with proprietary 21-section framework and 4-tier maturity scoring.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="ok",
        version="0.1.0",
        knowledge_base_loaded=_validate_knowledge_base(),
    )


@app.post("/api/v1/analyze", response_model=AnalysisSummaryResponse)
async def analyze_policy(
    file: Annotated[UploadFile, File(description="Cyber insurance policy PDF")],
    client_name: Annotated[str, Form()] = "",
    industry: Annotated[str, Form()] = "",
    annual_revenue: Annotated[str, Form()] = "",
    employee_count: Annotated[str, Form()] = "",
    is_msp: Annotated[bool, Form()] = False,
    notes: Annotated[str, Form()] = "",
):
    """Analyze a cyber insurance policy PDF.

    Accepts a PDF file upload with optional client metadata.
    Returns complete analysis with coverage scores, red flags,
    gap analysis, and a binding recommendation.
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

    # Save to temp directory
    analysis_id = uuid.uuid4().hex[:12]
    pdf_dir = settings.temp_dir / "uploads" / analysis_id
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / file.filename
    pdf_path.write_bytes(content)

    # Build client info
    client_info = ClientInfo(
        client_name=client_name,
        industry=industry,
        annual_revenue=annual_revenue,
        employee_count=employee_count,
        is_msp=is_msp,
        notes=notes,
    )

    # Run analysis
    try:
        engine = AnalysisEngine()
        analysis = engine.analyze_policy(pdf_path, client_info)

        # Store results
        _analyses[analysis.analysis_id] = analysis

        # Find the generated report PDF
        report_dir = settings.temp_dir / "reports"
        if report_dir.exists():
            pdfs = list(report_dir.glob(f"RhoneRisk_Analysis_*"))
            if pdfs:
                _report_paths[analysis.analysis_id] = pdfs[-1]

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
            report_pdf_url=f"/api/v1/analyze/{analysis.analysis_id}/report" if analysis.analysis_id in _report_paths or report_dir.exists() else None,
        )

    except Exception as e:
        logger.exception("Analysis failed for %s", analysis_id)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

    finally:
        # Clean up uploaded PDF
        shutil.rmtree(pdf_dir, ignore_errors=True)


@app.get("/api/v1/analyze/{analysis_id}")
async def get_analysis(analysis_id: str):
    """Get analysis results by ID."""
    if analysis_id not in _analyses:
        raise HTTPException(status_code=404, detail="Analysis not found.")

    analysis = _analyses[analysis_id]
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
        report_pdf_url=f"/api/v1/analyze/{analysis_id}/report" if analysis_id in _report_paths else None,
    )


@app.get("/api/v1/analyze/{analysis_id}/report")
async def download_report(analysis_id: str):
    """Download the generated PDF report."""
    if analysis_id not in _report_paths:
        raise HTTPException(status_code=404, detail="Report not found.")

    report_path = _report_paths[analysis_id]
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Report file missing.")

    return FileResponse(
        path=str(report_path),
        media_type="application/pdf",
        filename=report_path.name,
    )

from pydantic import BaseModel

from app.models.scoring import CoverageScore, CategorySummary, StrategicRecommendation, PolicyMetadata


class AnalysisStatusResponse(BaseModel):
    analysis_id: str
    status: str  # "pending", "extracting", "analyzing", "generating_report", "completed", "failed"
    progress: int = 0  # 0-100
    error: str | None = None


class AnalysisSummaryResponse(BaseModel):
    analysis_id: str
    status: str
    policy_metadata: PolicyMetadata
    overall_score: float
    overall_rating: str
    binding_recommendation: str
    binding_rationale: str
    coverage_scores: list[CoverageScore]
    red_flag_count: int
    critical_gaps: list[str]
    category_summaries: list[CategorySummary] = []
    strategic_recommendations: list[StrategicRecommendation] = []
    report_pdf_url: str | None = None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    knowledge_base_loaded: bool = False

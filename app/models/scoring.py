from pydantic import BaseModel, Field


class PolicyMetadata(BaseModel):
    policy_number: str = ""
    carrier_name: str = ""
    named_insured: str = ""
    effective_date: str = ""
    expiration_date: str = ""
    aggregate_limit: str = ""
    per_occurrence_limit: str = ""
    deductible: str = ""
    premium: str = ""
    retroactive_date: str = ""
    policy_form: str = ""
    waiting_period: str = ""
    continuity_date: str = ""
    extended_reporting_period: str = ""
    aggregate_retention: str = ""


class ScoringFactors(BaseModel):
    limit_adequacy: int | None = Field(None, ge=0, le=10)
    trigger_mechanism: int | None = Field(None, ge=0, le=10)
    exclusion_scope: int | None = Field(None, ge=0, le=10)
    sublimit_analysis: int | None = Field(None, ge=0, le=10)
    waiting_period: int | None = Field(None, ge=0, le=10)
    coinsurance: int | None = Field(None, ge=0, le=10)
    coverage_extensions: int | None = Field(None, ge=0, le=10)


class CoverageScore(BaseModel):
    coverage_name: str
    coverage_category: str = ""  # "third_party", "first_party", "cyber_crime", "policy_terms"
    coverage_subcategory: str = ""  # e.g. "incident_response", "regulatory", "business_interruption", "extortion", "ecrime", "additional"
    score: int = Field(ge=0, le=10)
    rating: str  # "Superior", "Average", "Basic", "No Coverage"
    limit: str = ""  # e.g. "$1,000,000 each Claim"
    retention: str = ""  # e.g. "$2,500"
    analysis: str = ""  # Detailed analysis paragraph explaining the reasoning
    recommendation: str = ""  # Specific recommendation for this coverage
    justification: str = ""  # Legacy field — kept for backward compatibility
    red_flags: list[str] = Field(default_factory=list)
    scoring_factors: ScoringFactors = Field(default_factory=ScoringFactors)
    key_provisions: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class CategorySummary(BaseModel):
    """Summary for a coverage category group."""
    category_key: str  # e.g. "third_party", "incident_response", "regulatory", etc.
    category_name: str  # Display name, e.g. "Third-Party Liability Coverages"
    average_score: float = 0.0
    assessment: str = ""  # One-line assessment for the category maturity table
    key_findings: list[str] = Field(default_factory=list)  # Bullet points of strengths and gaps


class StrategicRecommendation(BaseModel):
    """A strategic recommendation with priority and budget impact."""
    title: str
    priority: str = ""  # "High", "Medium", "Low"
    description: str = ""  # Detailed description of the recommendation
    action: str = ""  # Specific action to take
    budget_impact: str = ""  # Estimated budget impact
    timeframe: str = ""  # "immediate" or "medium_term"


class ReportSections(BaseModel):
    executive_summary: str = ""
    policy_overview: str = ""
    coverage_scoring_matrix: str = ""
    third_party_analysis: str = ""
    first_party_analysis: str = ""
    cyber_crime_analysis: str = ""
    policy_terms_analysis: str = ""
    exclusion_analysis: str = ""
    sublimit_analysis: str = ""
    gap_analysis: str = ""
    red_flag_summary: str = ""
    msp_specific_analysis: str = ""
    regulatory_compliance: str = ""
    incident_response_evaluation: str = ""
    business_interruption_analysis: str = ""
    social_engineering_analysis: str = ""
    vendor_dependency_analysis: str = ""
    benchmarking_analysis: str = ""
    scenario_analysis: str = ""
    recommendations: str = ""
    binding_recommendation: str = ""
    # New fields for enhanced report format
    policy_strengths: list[str] = Field(default_factory=list)
    areas_for_enhancement: list[str] = Field(default_factory=list)
    risk_management_items: list[str] = Field(default_factory=list)
    final_recommendation_detail: str = ""
    cost_benefit_analysis: str = ""


class PolicyAnalysis(BaseModel):
    analysis_id: str
    status: str = "completed"
    policy_metadata: PolicyMetadata
    coverage_scores: list[CoverageScore]
    overall_score: float = Field(ge=0, le=10)
    overall_rating: str
    binding_recommendation: str
    binding_rationale: str = ""
    report_sections: ReportSections
    red_flag_count: int = 0
    critical_gaps: list[str] = Field(default_factory=list)
    category_summaries: list[CategorySummary] = Field(default_factory=list)
    strategic_recommendations: list[StrategicRecommendation] = Field(default_factory=list)

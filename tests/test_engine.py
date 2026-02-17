"""Tests for the analysis engine with mocked Claude API."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.analysis.engine import AnalysisEngine
from app.models.requests import ClientInfo
from app.models.scoring import CoverageScore, ReportSections


@pytest.fixture
def mock_claude_response_scores():
    """Mock response for coverage scoring API call."""
    return [
        CoverageScore(
            coverage_name="Network Security Liability",
            coverage_category="third_party",
            score=7,
            rating="Average",
            justification="Standard network security coverage.",
            red_flags=[],
        ),
        CoverageScore(
            coverage_name="Privacy Liability",
            coverage_category="third_party",
            score=6,
            rating="Average",
            justification="Adequate privacy coverage.",
            red_flags=[],
        ),
        CoverageScore(
            coverage_name="Business Interruption - Cyber Event",
            coverage_category="first_party",
            score=5,
            rating="Average",
            justification="Standard BI coverage.",
            red_flags=[],
        ),
    ]


@pytest.fixture
def mock_report_sections():
    """Mock response for report narrative."""
    return ReportSections(
        executive_summary="This is a test executive summary.",
        policy_overview="Test policy overview.",
        coverage_scoring_matrix="Test coverage matrix.",
        third_party_analysis="Test third-party analysis.",
        first_party_analysis="Test first-party analysis.",
        cyber_crime_analysis="Test cyber crime analysis.",
        policy_terms_analysis="Test policy terms.",
        exclusion_analysis="Test exclusion analysis.",
        gap_analysis="Test gap analysis.",
        red_flag_summary="No red flags.",
        recommendations="Test recommendations.",
        binding_recommendation="Recommend binding.",
    )


@patch("app.analysis.engine.extract_policy")
@patch("app.analysis.engine.format_tables_for_context")
@patch("app.analysis.engine.generate_pdf_report")
def test_engine_pipeline(
    mock_pdf_gen,
    mock_format_tables,
    mock_extract,
    mock_claude_response_scores,
    mock_report_sections,
    sample_policy_text,
    tmp_path,
):
    """Test the full analysis pipeline with mocked dependencies."""
    # Setup mocks
    mock_extract.return_value = (sample_policy_text, [])
    mock_format_tables.return_value = ""
    mock_pdf_gen.return_value = tmp_path / "test.pdf"

    engine = AnalysisEngine()

    # Mock the Claude client
    engine.claude = MagicMock()
    engine.claude.score_coverages.return_value = mock_claude_response_scores
    engine.claude.generate_report_narrative.return_value = mock_report_sections

    # Create a dummy PDF path
    pdf_path = tmp_path / "test_policy.pdf"
    pdf_path.write_text("dummy pdf")

    # Run analysis
    result = engine.analyze_policy(
        pdf_path=pdf_path,
        client_info=ClientInfo(client_name="Test Corp"),
        output_dir=tmp_path,
    )

    assert result.analysis_id
    assert result.status == "completed"
    assert len(result.coverage_scores) == 3
    assert 0 <= result.overall_score <= 10
    assert result.overall_rating in ["Superior", "Average", "Basic", "No Coverage"]
    assert result.binding_recommendation

    # Verify API calls
    engine.claude.score_coverages.assert_called_once()
    engine.claude.generate_report_narrative.assert_called_once()

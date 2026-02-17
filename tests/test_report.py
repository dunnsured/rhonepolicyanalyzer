"""Tests for report generation."""

from app.report.generator import render_html_report, _score_color, _rating_badge_class


def test_score_color():
    assert _score_color(10) == "score-superior"
    assert _score_color(9) == "score-superior"
    assert _score_color(7) == "score-average"
    assert _score_color(5) == "score-average"
    assert _score_color(3) == "score-basic"
    assert _score_color(2) == "score-basic"
    assert _score_color(1) == "score-none"
    assert _score_color(0) == "score-none"


def test_rating_badge_class():
    assert _rating_badge_class("Superior") == "badge-superior"
    assert _rating_badge_class("Average") == "badge-average"
    assert _rating_badge_class("Basic") == "badge-basic"
    assert _rating_badge_class("No Coverage") == "badge-none"
    assert _rating_badge_class("Unknown") == "badge-none"


def test_render_html_report(sample_analysis):
    """Test that HTML report renders without errors."""
    html = render_html_report(sample_analysis)

    assert "RhôneRisk" in html or "Rh" in html
    assert "Acme Corporation" in html
    assert "CYB-2026-001234" in html
    assert "6.8" in html  # Overall score
    assert "Average" in html
    assert "BIND WITH CONDITIONS" in html  # Template renders recommendation in uppercase
    assert "Network Security Liability" in html
    assert "Social Engineering Fraud" in html
    assert "CONFIDENTIAL" in html


def test_render_html_contains_all_scores(sample_analysis):
    """Test that all coverage scores appear in the HTML."""
    html = render_html_report(sample_analysis)

    for score in sample_analysis.coverage_scores:
        assert score.coverage_name in html
        assert f"{score.score}/10" in html


def test_render_html_contains_sections(sample_analysis):
    """Test that narrative sections are included."""
    html = render_html_report(sample_analysis)

    assert "executive summary" in html.lower() or "Executive Summary" in html
    assert sample_analysis.report_sections.executive_summary in html

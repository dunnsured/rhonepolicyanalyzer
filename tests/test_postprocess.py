"""Tests for post-processing: red flag penalties, scoring, binding recommendations."""

from app.analysis.postprocess import (
    _score_to_rating,
    apply_red_flag_penalties,
    calculate_overall_score,
    determine_binding_recommendation,
)
from app.models.scoring import CoverageScore, ScoringFactors


def test_score_to_rating():
    assert _score_to_rating(10) == "Superior"
    assert _score_to_rating(9) == "Superior"
    assert _score_to_rating(8) == "Average"
    assert _score_to_rating(5) == "Average"
    assert _score_to_rating(4) == "Basic"
    assert _score_to_rating(2) == "Basic"
    assert _score_to_rating(1) == "No Coverage"
    assert _score_to_rating(0) == "No Coverage"


def test_apply_red_flag_penalties_social_engineering(sample_coverage_scores):
    """Social engineering sublimit red flag should cap affected scores."""
    scores = apply_red_flag_penalties(sample_coverage_scores)

    # Find the social engineering score
    se_score = next(s for s in scores if "Social Engineering" in s.coverage_name)
    assert se_score.score <= 6  # Capped by social_engineering_sublimit rule


def test_apply_red_flag_no_false_positives():
    """Scores without red flags should not be modified."""
    scores = [
        CoverageScore(
            coverage_name="Network Security Liability",
            coverage_category="third_party",
            score=9,
            rating="Superior",
            justification="Excellent coverage.",
            red_flags=[],
        )
    ]
    result = apply_red_flag_penalties(scores)
    assert result[0].score == 9


def test_calculate_overall_score(sample_coverage_scores):
    overall, rating = calculate_overall_score(sample_coverage_scores)
    assert 0 <= overall <= 10
    assert rating in ["Superior", "Average", "Basic", "No Coverage"]


def test_calculate_overall_score_empty():
    overall, rating = calculate_overall_score([])
    assert overall == 0.0
    assert rating == "No Coverage"


def test_binding_recommend_binding():
    rec, rationale = determine_binding_recommendation(8.5, 0, [])
    assert rec == "Recommend Binding"
    assert "8.5" in rationale


def test_binding_bind_with_conditions():
    rec, rationale = determine_binding_recommendation(6.0, 2, [])
    assert rec == "Bind with Conditions"


def test_binding_require_modifications():
    rec, rationale = determine_binding_recommendation(3.5, 5, ["Gap 1", "Gap 2"])
    assert rec == "Require Major Modifications"


def test_binding_recommend_decline():
    rec, rationale = determine_binding_recommendation(2.0, 8, ["Gap 1", "Gap 2", "Gap 3"])
    assert rec == "Recommend Decline"


def test_war_exclusion_penalty():
    """War exclusion red flag should cap all scores at 6."""
    scores = [
        CoverageScore(
            coverage_name="Network Security Liability",
            coverage_category="third_party",
            score=9,
            rating="Superior",
            justification="Great coverage.",
            red_flags=["War exclusion without buyback - act of war excluded"],
        ),
        CoverageScore(
            coverage_name="Privacy Liability",
            coverage_category="third_party",
            score=8,
            rating="Average",
            justification="Good coverage.",
            red_flags=[],
        ),
    ]
    result = apply_red_flag_penalties(scores)
    # War exclusion affects "all" coverages, cap at 6
    assert result[0].score <= 6
    assert result[1].score <= 6

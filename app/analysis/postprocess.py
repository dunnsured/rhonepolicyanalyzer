"""Post-processing: red flag penalties, score normalization, and binding recommendation."""

import logging
from pathlib import Path

import yaml

from app.config import get_settings
from app.models.scoring import CoverageScore

logger = logging.getLogger(__name__)


def _load_red_flags() -> list[dict]:
    """Load red flag rules from YAML."""
    path = get_settings().knowledge_dir / "red_flags.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    return data["red_flags"]


def _load_scoring_methodology() -> dict:
    """Load scoring methodology from YAML."""
    path = get_settings().knowledge_dir / "scoring_methodology.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def apply_red_flag_penalties(scores: list[CoverageScore]) -> list[CoverageScore]:
    """Apply deterministic red flag score caps based on rules.

    Red flags identified by the AI are cross-referenced with the rules YAML.
    If a red flag matches, the affected coverage scores are capped.

    Args:
        scores: List of AI-generated coverage scores.

    Returns:
        Updated scores with penalties applied.
    """
    red_flag_rules = _load_red_flags()

    # Build a lookup of coverage key -> score object
    score_map: dict[str, CoverageScore] = {}
    for s in scores:
        # Normalize coverage name to key format
        key = s.coverage_name.lower().replace(" ", "_").replace("-", "_").replace("/", "_")
        score_map[key] = s

    for rule in red_flag_rules:
        rule_id = rule["id"]
        max_cap = rule["max_score_cap"]
        affected = rule["affected_coverages"]

        # Check if any score identified this red flag
        flag_found = False
        for s in scores:
            for rf in s.red_flags:
                rf_lower = rf.lower()
                if any(kw in rf_lower for kw in rule.get("detection_keywords", [])):
                    flag_found = True
                    break
            if flag_found:
                break

        if not flag_found:
            continue

        logger.info("Red flag detected: %s (cap: %d)", rule["name"], max_cap)

        # Apply cap to affected coverages
        for s in scores:
            key = s.coverage_name.lower().replace(" ", "_").replace("-", "_").replace("/", "_")
            should_cap = "all" in affected or any(a in key for a in affected)

            if should_cap and s.score > max_cap:
                logger.info(
                    "Capping %s from %d to %d due to %s",
                    s.coverage_name, s.score, max_cap, rule["name"],
                )
                s.score = max_cap
                s.rating = _score_to_rating(max_cap)
                if rule["name"] not in s.red_flags:
                    s.red_flags.append(rule["name"])

    return scores


def _score_to_rating(score: int) -> str:
    """Convert a numeric score to a rating tier."""
    if score >= 9:
        return "Superior"
    elif score >= 5:
        return "Average"
    elif score >= 2:
        return "Basic"
    else:
        return "No Coverage"


def calculate_overall_score(scores: list[CoverageScore]) -> tuple[float, str]:
    """Calculate the weighted overall policy maturity score.

    Weights: Coverage Adequacy (40%), Limit Sufficiency (25%),
             Exclusion Analysis (20%), Policy Terms (15%).

    Since AI scores each coverage holistically, we approximate the dimension
    scores from the coverage scores and their scoring factors.

    Args:
        scores: List of all coverage scores.

    Returns:
        Tuple of (overall_score, overall_rating).
    """
    if not scores:
        return 0.0, "No Coverage"

    methodology = _load_scoring_methodology()
    weights = methodology["overall_score_weights"]

    # Calculate dimension scores from coverage scores and their factors
    coverage_scores = []
    limit_scores = []
    exclusion_scores = []
    terms_scores = []

    for s in scores:
        coverage_scores.append(s.score)

        # Use scoring factors if available, otherwise use the overall score
        factors = s.scoring_factors
        if factors.limit_adequacy is not None:
            limit_scores.append(factors.limit_adequacy)
        else:
            limit_scores.append(s.score)

        if factors.exclusion_scope is not None:
            exclusion_scores.append(factors.exclusion_scope)
        else:
            exclusion_scores.append(s.score)

        # Terms score from trigger + waiting period + coinsurance factors
        terms_vals = [
            v for v in [factors.trigger_mechanism, factors.waiting_period, factors.coinsurance]
            if v is not None
        ]
        if terms_vals:
            terms_scores.append(sum(terms_vals) / len(terms_vals))
        else:
            terms_scores.append(s.score)

    def avg(lst: list) -> float:
        return sum(lst) / len(lst) if lst else 0.0

    overall = (
        avg(coverage_scores) * weights["coverage_adequacy"]
        + avg(limit_scores) * weights["limit_sufficiency"]
        + avg(exclusion_scores) * weights["exclusion_analysis"]
        + avg(terms_scores) * weights["policy_terms"]
    )

    overall = round(overall, 1)
    rating = _score_to_rating(round(overall))

    logger.info("Overall score: %.1f (%s)", overall, rating)
    return overall, rating


def determine_binding_recommendation(
    overall_score: float,
    red_flag_count: int,
    critical_gaps: list[str],
) -> tuple[str, str]:
    """Determine the binding recommendation based on score and red flags.

    Args:
        overall_score: Weighted overall policy score.
        red_flag_count: Total number of red flags identified.
        critical_gaps: List of critical gap descriptions.

    Returns:
        Tuple of (recommendation, rationale).
    """
    methodology = _load_scoring_methodology()
    recs = methodology["binding_recommendations"]

    if overall_score >= recs["recommend_binding"]["overall_score_min"] and red_flag_count == 0:
        rec = "Recommend Binding"
        rationale = (
            f"Policy achieves an overall maturity score of {overall_score}/10 with no critical red flags. "
            "Coverage meets or exceeds RhôneRisk standards across all evaluated dimensions."
        )
    elif overall_score >= recs["bind_with_conditions"]["overall_score_min"]:
        rec = "Bind with Conditions"
        conditions = f"{red_flag_count} red flag(s) identified" if red_flag_count else "some areas need improvement"
        rationale = (
            f"Policy achieves a score of {overall_score}/10 but {conditions}. "
            "Recommend binding with negotiated improvements to address identified gaps."
        )
    elif overall_score >= recs["require_major_modifications"]["overall_score_min"]:
        rec = "Require Major Modifications"
        rationale = (
            f"Policy scores {overall_score}/10 with {red_flag_count} red flag(s) and "
            f"{len(critical_gaps)} critical gap(s). Substantial modifications required before binding."
        )
    else:
        rec = "Recommend Decline"
        rationale = (
            f"Policy scores {overall_score}/10, which is fundamentally inadequate. "
            f"{red_flag_count} red flag(s) and {len(critical_gaps)} critical gap(s) identified. "
            "Recommend declining this policy and seeking alternatives."
        )

    logger.info("Binding recommendation: %s", rec)
    return rec, rationale

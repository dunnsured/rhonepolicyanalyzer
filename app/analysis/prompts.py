"""Prompt building utilities for the analysis pipeline."""

import json
from app.models.scoring import PolicyMetadata, CoverageScore
from app.models.requests import ClientInfo


def format_metadata_context(metadata: PolicyMetadata) -> str:
    """Format policy metadata as context for AI prompts."""
    lines = []
    if metadata.policy_number:
        lines.append(f"- Policy Number: {metadata.policy_number}")
    if metadata.carrier_name:
        lines.append(f"- Carrier: {metadata.carrier_name}")
    if metadata.named_insured:
        lines.append(f"- Named Insured: {metadata.named_insured}")
    if metadata.effective_date:
        lines.append(f"- Effective Date: {metadata.effective_date}")
    if metadata.expiration_date:
        lines.append(f"- Expiration Date: {metadata.expiration_date}")
    if metadata.aggregate_limit:
        lines.append(f"- Aggregate Limit: ${metadata.aggregate_limit}")
    if metadata.per_occurrence_limit:
        lines.append(f"- Per Occurrence Limit: ${metadata.per_occurrence_limit}")
    if metadata.deductible:
        lines.append(f"- Deductible/Retention: ${metadata.deductible}")
    if metadata.premium:
        lines.append(f"- Annual Premium: ${metadata.premium}")
    if metadata.retroactive_date:
        lines.append(f"- Retroactive Date: {metadata.retroactive_date}")
    if metadata.policy_form:
        lines.append(f"- Policy Form: {metadata.policy_form}")

    return "\n".join(lines) if lines else "No metadata could be automatically extracted."


def format_scores_context(scores: list[CoverageScore]) -> str:
    """Format coverage scores as context for the report narrative prompt."""
    score_dicts = []
    for s in scores:
        d = {
            "coverage_name": s.coverage_name,
            "category": s.coverage_category,
            "score": s.score,
            "rating": s.rating,
            "justification": s.justification,
            "red_flags": s.red_flags,
            "recommendations": s.recommendations,
        }
        score_dicts.append(d)
    return json.dumps(score_dicts, indent=2)


def format_client_context(client_info: ClientInfo) -> str:
    """Format client information as context for AI prompts."""
    lines = []
    if client_info.client_name:
        lines.append(f"- Client Name: {client_info.client_name}")
    if client_info.industry:
        lines.append(f"- Industry: {client_info.industry}")
    if client_info.annual_revenue:
        lines.append(f"- Annual Revenue: {client_info.annual_revenue}")
    if client_info.employee_count:
        lines.append(f"- Employee Count: {client_info.employee_count}")
    if client_info.is_msp:
        lines.append("- Client Type: MSP (Managed Service Provider) — apply MSP-specific scoring emphasis")
    if client_info.notes:
        lines.append(f"- Additional Notes: {client_info.notes}")

    return "\n".join(lines) if lines else "No client information provided."

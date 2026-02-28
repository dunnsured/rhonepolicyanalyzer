"""Anthropic Claude API client with streaming, structured outputs, and retries."""

import json
import logging
import time
import traceback
from pathlib import Path

import anthropic
import httpx

from app.config import get_settings
from app.models.scoring import (
    CoverageScore,
    ReportSections,
    CategorySummary,
    StrategicRecommendation,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool schema: Coverage Scoring (Call 1) — unchanged structure
# ---------------------------------------------------------------------------
COVERAGE_SCORES_TOOL = {
    "name": "submit_coverage_scores",
    "description": "Submit the complete set of coverage scores with detailed per-coverage analysis for the policy.",
    "input_schema": {
        "type": "object",
        "properties": {
            "coverage_scores": {
                "type": "array",
                "description": "Array of detailed scores for each coverage type found in the policy.",
                "items": {
                    "type": "object",
                    "properties": {
                        "coverage_name": {
                            "type": "string",
                            "description": "Name of the coverage type."
                        },
                        "coverage_category": {
                            "type": "string",
                            "enum": ["third_party", "first_party", "cyber_crime"],
                        },
                        "coverage_subcategory": {
                            "type": "string",
                            "enum": [
                                "liability", "incident_response", "regulatory",
                                "business_interruption", "extortion", "ecrime", "additional"
                            ],
                        },
                        "score": {
                            "type": "integer", "minimum": 0, "maximum": 10,
                        },
                        "rating": {
                            "type": "string",
                            "enum": ["Superior", "Average", "Basic", "No Coverage"],
                        },
                        "limit": {
                            "type": "string",
                            "description": "Coverage limit as stated in the policy. Use 'N/A' if not applicable."
                        },
                        "retention": {
                            "type": "string",
                            "description": "Retention/deductible for this coverage."
                        },
                        "analysis": {
                            "type": "string",
                            "description": "2-4 sentence analysis: what the coverage does, score rationale, limit adequacy vs recommended minimums, and notable features/concerns."
                        },
                        "recommendation": {
                            "type": "string",
                            "description": "Specific recommendation if applicable. Empty string if none."
                        },
                        "red_flags": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "scoring_factors": {
                            "type": "object",
                            "properties": {
                                "limit_adequacy": {"type": "integer", "minimum": 0, "maximum": 10},
                                "trigger_mechanism": {"type": "integer", "minimum": 0, "maximum": 10},
                                "exclusion_scope": {"type": "integer", "minimum": 0, "maximum": 10},
                                "sublimit_analysis": {"type": "integer", "minimum": 0, "maximum": 10},
                                "waiting_period": {"type": "integer", "minimum": 0, "maximum": 10},
                                "coinsurance": {"type": "integer", "minimum": 0, "maximum": 10},
                                "coverage_extensions": {"type": "integer", "minimum": 0, "maximum": 10},
                            },
                        },
                        "key_provisions": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "recommendations": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": [
                        "coverage_name", "coverage_category", "coverage_subcategory",
                        "score", "rating", "limit", "retention", "analysis", "red_flags"
                    ],
                },
            },
            "category_summaries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "category_key": {"type": "string"},
                        "category_name": {"type": "string"},
                        "average_score": {"type": "number"},
                        "assessment": {"type": "string"},
                        "key_findings": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["category_key", "category_name", "average_score", "assessment", "key_findings"],
                },
            },
        },
        "required": ["coverage_scores", "category_summaries"],
    },
}

# ---------------------------------------------------------------------------
# Tool schema: Report Narrative (Call 2) — RESTRUCTURED for efficiency
# ---------------------------------------------------------------------------
# Key changes:
# - scenario_analysis and benchmarking_analysis REMOVED (computed in Python)
# - All sections target concise, table-heavy output
# - Reduced from ~32K to ~16K max_tokens
REPORT_NARRATIVE_TOOL = {
    "name": "submit_report_narrative",
    "description": "Submit the narrative content for all report sections.",
    "input_schema": {
        "type": "object",
        "properties": {
            "executive_summary": {
                "type": "string",
                "description": "2-3 paragraph C-suite overview: overall maturity score, key metrics (coverages scored, red flags, critical gaps), binding recommendation, and 3-4 sentence strategic context."
            },
            "policy_overview": {
                "type": "string",
                "description": "Concise policy declarations: carrier, policy number, effective/expiration dates, aggregate limit, per-occurrence limit, deductible, retroactive date, premium. Use a markdown table."
            },
            "exclusion_analysis": {
                "type": "string",
                "description": "Markdown table of all exclusions with columns: Exclusion | Severity (Critical/Major/Moderate) | Carve-Back Available | Impact Assessment. Then 1-2 paragraphs of key concerns."
            },
            "gap_analysis": {
                "type": "string",
                "description": "Coverage gaps as a markdown table with columns: Gap | Severity (Critical/Major/Moderate/Minor) | Estimated Exposure | Recommended Action. Group by severity."
            },
            "red_flag_summary": {
                "type": "string",
                "description": "Markdown table of all red flags with columns: Red Flag | Affected Coverages | Score Impact | Recommended Mitigation."
            },
            "policy_terms_analysis": {
                "type": "string",
                "description": "Concise analysis of: claims handling, defense provisions, settlement authority, panel requirements, ERP, cancellation, M&A provisions. Use a favorable/unfavorable terms table."
            },
            "recommendations": {
                "type": "string",
                "description": "Prioritized recommendations as a markdown table with columns: # | Recommendation | Priority (High/Medium/Low) | Timeline | Est. Premium Impact. Group by timeline: Immediate (0-30d), Short-term (30-90d), Long-term (90+d)."
            },
            "binding_recommendation": {
                "type": "string",
                "description": "Clear binding recommendation (Recommend Binding / Bind with Conditions / Require Major Modifications / Recommend Decline) with 2-3 sentence rationale."
            },
            "policy_strengths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "5-8 concise bullet points of policy strengths."
            },
            "areas_for_enhancement": {
                "type": "array",
                "items": {"type": "string"},
                "description": "4-6 bullet points identifying specific gaps or weaknesses."
            },
            "strategic_recommendations": {
                "type": "array",
                "description": "4-6 strategic recommendations with priority levels.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "priority": {"type": "string", "enum": ["High", "Medium", "Low"]},
                        "description": {"type": "string", "description": "1-2 sentence description."},
                        "action": {"type": "string"},
                        "budget_impact": {"type": "string"},
                        "timeframe": {"type": "string", "enum": ["immediate", "medium_term"]},
                    },
                    "required": ["title", "priority", "description", "action", "budget_impact", "timeframe"],
                },
            },
            "risk_management_items": {
                "type": "array",
                "items": {"type": "string"},
                "description": "4-6 risk management recommendations. Each 2-3 sentences."
            },
            "final_recommendation_detail": {
                "type": "string",
                "description": "Final recommendation paragraph: recommended action, 3-5 numbered priority items, budget impact summary, value proposition."
            },
            "cost_benefit_analysis": {
                "type": "string",
                "description": "Markdown table comparing current premium vs recommended enhancements: Enhancement | Additional Premium Est. | Risk Reduction | ROI Assessment. Include total row."
            },
        },
        "required": [
            "executive_summary", "policy_overview",
            "exclusion_analysis", "gap_analysis", "red_flag_summary",
            "recommendations", "binding_recommendation",
            "policy_strengths", "areas_for_enhancement", "strategic_recommendations",
            "risk_management_items", "final_recommendation_detail",
        ],
    },
}


class ClaudeClient:
    """Wrapper around the Anthropic SDK with streaming, retries, and structured outputs."""

    def __init__(self):
        settings = get_settings()
        self.client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            max_retries=0,
        )
        self.model = settings.claude_model
        self.max_tokens = settings.claude_max_tokens
        self._system_prompt: str | None = None

    @property
    def system_prompt(self) -> str:
        if self._system_prompt is None:
            prompt_path = get_settings().knowledge_dir / "system_prompt.md"
            self._system_prompt = prompt_path.read_text()
            logger.info("Loaded system prompt: %d chars", len(self._system_prompt))
        return self._system_prompt

    def _stream_with_retry(
        self,
        *,
        system: list[dict],
        messages: list[dict],
        tools: list[dict],
        tool_choice: dict,
        max_tokens: int | None = None,
        max_retries: int = 3,
    ) -> tuple[anthropic.types.Message, dict]:
        """Make a streaming API call with exponential backoff retry."""
        tokens = max_tokens or self.max_tokens
        last_error = None

        for attempt in range(max_retries):
            call_start = time.time()
            try:
                logger.info(
                    "Claude API streaming call attempt %d/%d (model=%s, max_tokens=%d)",
                    attempt + 1, max_retries, self.model, tokens,
                )
                with self.client.messages.stream(
                    model=self.model,
                    max_tokens=tokens,
                    system=system,
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                ) as stream:
                    response = stream.get_final_message()

                call_duration = time.time() - call_start
                usage = {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "duration_seconds": round(call_duration, 2),
                }
                logger.info(
                    "API call succeeded in %.1fs: %d input tokens, %d output tokens, stop_reason=%s",
                    call_duration,
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                    response.stop_reason,
                )
                return response, usage

            except anthropic.APIConnectionError as e:
                call_duration = time.time() - call_start
                last_error = e
                if attempt < max_retries - 1:
                    wait = 2 ** attempt * 5
                    logger.warning(
                        "Connection error after %.1fs, retrying in %ds (attempt %d/%d): %s",
                        call_duration, wait, attempt + 1, max_retries, e,
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        "Connection error after %.1fs, all retries exhausted: %s\n%s",
                        call_duration, e, traceback.format_exc(),
                    )

            except anthropic.RateLimitError as e:
                call_duration = time.time() - call_start
                last_error = e
                if attempt < max_retries - 1:
                    wait = 2 ** attempt * 10
                    logger.warning(
                        "Rate limited after %.1fs, waiting %ds (attempt %d/%d): %s",
                        call_duration, wait, attempt + 1, max_retries, e,
                    )
                    time.sleep(wait)
                else:
                    logger.error("Rate limited, all retries exhausted: %s", e)

            except anthropic.APIStatusError as e:
                call_duration = time.time() - call_start
                last_error = e
                if (e.status_code >= 500 or e.status_code == 529) and attempt < max_retries - 1:
                    wait = 2 ** attempt * 10
                    logger.warning(
                        "Server error %d after %.1fs, retrying in %ds (attempt %d/%d): %s",
                        e.status_code, call_duration, wait, attempt + 1, max_retries, e,
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        "API error %d after %.1fs: %s\n%s",
                        e.status_code, call_duration, e, traceback.format_exc(),
                    )
                    raise

            except anthropic.APITimeoutError as e:
                call_duration = time.time() - call_start
                last_error = e
                if attempt < max_retries - 1:
                    wait = 2 ** attempt * 5
                    logger.warning(
                        "Timeout after %.1fs, retrying in %ds (attempt %d/%d): %s",
                        call_duration, wait, attempt + 1, max_retries, e,
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        "Timeout after %.1fs, all retries exhausted: %s",
                        call_duration, e,
                    )

            except Exception as e:
                call_duration = time.time() - call_start
                last_error = e
                logger.error(
                    "Unexpected error after %.1fs (attempt %d/%d): %s\n%s",
                    call_duration, attempt + 1, max_retries, e, traceback.format_exc(),
                )
                if attempt >= max_retries - 1:
                    raise

        raise RuntimeError(f"Max retries ({max_retries}) exceeded for Claude API call. Last error: {last_error}")

    def _extract_tool_input(self, response: anthropic.types.Message) -> dict:
        """Extract the tool use input from a response."""
        for block in response.content:
            if block.type == "tool_use":
                return block.input

        if response.stop_reason == "max_tokens":
            logger.warning("Response truncated (max_tokens). Attempting partial JSON recovery.")
            for block in response.content:
                if block.type == "text":
                    text = block.text
                    brace_start = text.find("{")
                    if brace_start >= 0:
                        partial_json = text[brace_start:]
                        recovered = self._try_recover_json(partial_json)
                        if recovered:
                            logger.info("Recovered partial JSON with %d top-level keys", len(recovered))
                            return recovered

        content_types = [block.type for block in response.content]
        logger.error("No tool_use block found. Got content types: %s, stop_reason: %s",
                      content_types, response.stop_reason)
        if response.content and response.content[0].type == "text":
            logger.error("Text content (first 500 chars): %s", response.content[0].text[:500])
        raise ValueError(f"No tool_use block found in response. Content types: {content_types}, stop_reason: {response.stop_reason}")

    def _try_recover_json(self, partial: str) -> dict | None:
        """Try to recover a valid JSON object from a truncated string."""
        try:
            return json.loads(partial)
        except json.JSONDecodeError:
            pass

        for trim_chars in range(1, min(5000, len(partial))):
            candidate = partial[:-trim_chars]
            for suffix in ['"}', '"]', '}', ']', '"}]', '"}]}', '"}]}}']:
                try:
                    result = json.loads(candidate + suffix)
                    if isinstance(result, dict):
                        return result
                except json.JSONDecodeError:
                    continue

        logger.error("Could not recover partial JSON (length=%d)", len(partial))
        return None

    def score_coverages(self, policy_text: str, tables_text: str,
                        metadata_context: str, client_context: str = "") -> tuple[list[CoverageScore], list[CategorySummary], dict]:
        """Call 1: Score all coverage types with detailed per-coverage analysis.

        Returns:
            Tuple of (list of CoverageScore, list of CategorySummary, usage dict).
        """
        logger.info("Starting coverage scoring (Call 1) — using streaming")

        system = [{"type": "text", "text": self.system_prompt}]

        client_section = ""
        if client_context:
            client_section = f"""
## Client Information
{client_context}
"""

        user_message = f"""Analyze the following cyber insurance policy and score ALL coverage types using the RhôneRisk Maturity Scoring System.
{client_section}
## Pre-Parsed Policy Metadata
{metadata_context}

## Full Policy Text
{policy_text}

{tables_text}

## Instructions
1. Score EVERY coverage type listed in the methodology (all 21 types across third-party, first-party, and cyber crime categories).
2. For coverages not explicitly found in the policy, score them as 0 (No Coverage).
3. For EACH coverage, provide:
   - The **limit** as stated in the policy
   - The **retention/deductible**
   - A **concise analysis** (2-4 sentences): score rationale, limit vs recommended minimums from the framework, and notable features/concerns
   - A specific **recommendation** if applicable
   - Apply the **weighted maturity scoring**: Coverage Comprehensiveness (40%), Limit Adequacy (30%), Terms & Conditions (20%), Carrier Quality (10%)
4. Compare limits against the **Recommended Minimum Limits** table in the framework.
5. Identify ALL red flags per the red flag rules.
6. For each category group, provide a **category summary** with average score, one-line assessment, and 3-5 key findings.

Use the submit_coverage_scores tool to return your complete analysis."""

        messages = [{"role": "user", "content": user_message}]

        logger.info("Scoring call — system: %d chars, user: %d chars", len(self.system_prompt), len(user_message))

        response, usage = self._stream_with_retry(
            system=system,
            messages=messages,
            tools=[COVERAGE_SCORES_TOOL],
            tool_choice={"type": "tool", "name": "submit_coverage_scores"},
            max_tokens=16384,
        )

        result = self._extract_tool_input(response)
        scores = [CoverageScore(**s) for s in result["coverage_scores"]]
        summaries = [CategorySummary(**cs) for cs in result.get("category_summaries", [])]
        logger.info("Scored %d coverage types, %d category summaries in %.1fs",
                     len(scores), len(summaries), usage["duration_seconds"])
        return scores, summaries, usage

    def generate_report_narrative(
        self,
        policy_text: str,
        tables_text: str,
        metadata_context: str,
        scores_context: str,
        client_context: str,
        risk_quantification_md: str = "",
    ) -> tuple[ReportSections, list[StrategicRecommendation], dict]:
        """Call 2: Generate narrative content for all report sections via streaming.

        Uses 16K max_tokens (down from 32K) — risk quantification and benchmarking
        are pre-computed in Python and injected as context.

        Returns:
            Tuple of (ReportSections, list of StrategicRecommendation, usage dict).
        """
        logger.info("Starting report narrative generation (Call 2) — using streaming")

        system = [{"type": "text", "text": self.system_prompt}]

        rq_section = ""
        if risk_quantification_md:
            rq_section = f"""
## Pre-Computed Risk Quantification (DO NOT regenerate — reference these numbers)
{risk_quantification_md}
"""

        user_message = f"""Generate the narrative content for a RhôneRisk cyber insurance policy analysis report.

## Client Information
{client_context}

## Pre-Parsed Policy Metadata
{metadata_context}

## Coverage Scores (from analysis)
{scores_context}
{rq_section}
## Full Policy Text
{policy_text}

{tables_text}

## CRITICAL: Output Format Rules
- Use **markdown tables** for structured data (exclusions, gaps, red flags, recommendations, cost-benefit)
- Keep prose sections to **2-3 paragraphs max**
- Be **specific**: cite policy language, dollar amounts, and page references
- Be **concise**: no filler, no repetition
- Reference the **pre-computed risk quantification numbers** for scenario analysis — do NOT recalculate them
- Compare limits against the **Recommended Minimum Limits** and **Industry Benchmarks** from the framework

## Required Sections

1. **Executive Summary**: 2-3 paragraphs. Include: overall maturity score, binding recommendation, key metrics (coverages scored, red flags, critical gaps), and strategic context.

2. **Policy Overview**: Markdown table of declarations (carrier, policy number, dates, limits, deductible, premium, retroactive date).

3. **Exclusion Analysis**: Markdown table — Exclusion | Severity | Carve-Back | Impact. Then 1-2 paragraphs on key concerns.

4. **Gap Analysis**: Markdown table — Gap | Severity | Estimated Exposure | Recommended Action. Group by severity.

5. **Red Flag Summary**: Markdown table — Red Flag | Affected Coverages | Score Impact | Mitigation.

6. **Policy Terms Analysis**: Favorable vs unfavorable terms table. Brief analysis of claims handling, defense, ERP, panel requirements.

7. **Recommendations**: Markdown table — # | Recommendation | Priority | Timeline | Est. Premium Impact. Group by timeline.

8. **Binding Recommendation**: Clear recommendation with 2-3 sentence rationale.

9. **Cost-Benefit Analysis**: Markdown table — Enhancement | Additional Premium Est. | Risk Reduction | ROI Assessment. Include total row.

10. **Policy Strengths**: 5-8 bullet points.
11. **Areas for Enhancement**: 4-6 bullet points.
12. **Strategic Recommendations**: 4-6 structured recommendations (title, priority, description, action, budget_impact, timeframe).
13. **Risk Management Items**: 4-6 items, each 2-3 sentences.
14. **Final Recommendation Detail**: Paragraph with numbered priority items and budget summary.

Use the submit_report_narrative tool to return all content."""

        messages = [{"role": "user", "content": user_message}]

        logger.info("Narrative call — system: %d chars, user: %d chars", len(self.system_prompt), len(user_message))

        response, usage = self._stream_with_retry(
            system=system,
            messages=messages,
            tools=[REPORT_NARRATIVE_TOOL],
            tool_choice={"type": "tool", "name": "submit_report_narrative"},
            max_tokens=16384,
        )

        result = self._extract_tool_input(response)

        # Extract strategic recommendations separately
        strategic_recs_raw = result.pop("strategic_recommendations", [])
        strategic_recs = [StrategicRecommendation(**sr) for sr in strategic_recs_raw]

        # Normalize list fields
        list_fields = ["policy_strengths", "areas_for_enhancement", "risk_management_items"]
        for field in list_fields:
            val = result.get(field)
            if isinstance(val, str) and val.strip():
                lines = []
                for line in val.split("\n"):
                    line = line.strip()
                    if line.startswith(("- ", "* ", "• ")):
                        line = line[2:].strip()
                    elif len(line) > 2 and line[0].isdigit() and "." in line[:4]:
                        dot_pos = line.index(".")
                        line = line[dot_pos + 1:].strip()
                    if line:
                        lines.append(line)
                result[field] = lines
                logger.info("Normalized '%s' from string to list with %d items", field, len(lines))
            elif val is None:
                result[field] = []

        # Remove any extra keys not in ReportSections
        valid_fields = set(ReportSections.model_fields.keys())
        filtered_result = {k: v for k, v in result.items() if k in valid_fields}

        sections = ReportSections(**filtered_result)
        logger.info("Generated report narrative for %d sections, %d strategic recs in %.1fs",
                     sum(1 for v in filtered_result.values() if v), len(strategic_recs), usage["duration_seconds"])
        return sections, strategic_recs, usage

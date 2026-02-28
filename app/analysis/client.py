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
# Tool schema: Coverage Scoring (Call 1)
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
                            "description": "Name of the coverage type, e.g. 'Tech & Professional Services Liability', 'Breach Response Costs'."
                        },
                        "coverage_category": {
                            "type": "string",
                            "enum": ["third_party", "first_party", "cyber_crime"],
                            "description": "Top-level category."
                        },
                        "coverage_subcategory": {
                            "type": "string",
                            "enum": [
                                "liability",
                                "incident_response",
                                "regulatory",
                                "business_interruption",
                                "extortion",
                                "ecrime",
                                "additional"
                            ],
                            "description": "Subcategory within the top-level category. Use 'liability' for third-party coverages. For first-party use: incident_response, regulatory, business_interruption, extortion, additional. For cyber_crime use: ecrime."
                        },
                        "score": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 10,
                            "description": "Maturity score from 0-10."
                        },
                        "rating": {
                            "type": "string",
                            "enum": ["Superior", "Average", "Basic", "No Coverage"],
                            "description": "Rating tier: Superior (9-10), Average (5-8), Basic (2-4), No Coverage (0-1)."
                        },
                        "limit": {
                            "type": "string",
                            "description": "Coverage limit as stated in the policy, e.g. '$1,000,000 each Claim', '$250,000 each loss'. Use 'N/A' if not applicable."
                        },
                        "retention": {
                            "type": "string",
                            "description": "Retention/deductible for this coverage, e.g. '$2,500', '$0', 'N/A'."
                        },
                        "analysis": {
                            "type": "string",
                            "description": "Detailed analysis paragraph (3-6 sentences) explaining: what the coverage does, why the limit is adequate/inadequate for this specific client, comparison to industry standards, and any notable features or concerns. Write as a senior insurance analyst would for a client-facing report."
                        },
                        "recommendation": {
                            "type": "string",
                            "description": "Specific recommendation for this coverage if applicable (e.g. 'Consider increasing to $2-3M if budget allows'). Leave empty string if no specific recommendation needed."
                        },
                        "red_flags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of red flags identified for this coverage."
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
                            "description": "Individual scoring factor breakdown."
                        },
                        "key_provisions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Key policy provisions affecting this coverage."
                        },
                        "recommendations": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of specific recommendations for improving this coverage."
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
                "description": "Summary for each coverage category/subcategory grouping.",
                "items": {
                    "type": "object",
                    "properties": {
                        "category_key": {
                            "type": "string",
                            "description": "Key matching the subcategory or top-level category, e.g. 'third_party', 'incident_response', 'regulatory', 'business_interruption', 'extortion', 'ecrime', 'additional'."
                        },
                        "category_name": {
                            "type": "string",
                            "description": "Display name, e.g. 'Third-Party Liability Coverages', 'Incident Response & Breach Costs', 'eCrime Coverages'."
                        },
                        "average_score": {
                            "type": "number",
                            "description": "Average maturity score for coverages in this category."
                        },
                        "assessment": {
                            "type": "string",
                            "description": "One-line assessment for the category maturity table, e.g. 'Strong comprehensive liability coverage with opportunity to increase key limits'."
                        },
                        "key_findings": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "3-6 bullet points of key findings: strengths, gaps, and notable features for this category."
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
# Tool schema: Report Narrative (Call 2) — Streamlined
# ---------------------------------------------------------------------------
# The per-coverage detailed analysis is already captured in Call 1 (analysis
# paragraphs in each CoverageScore). This call focuses on report-level
# narrative sections that provide cross-cutting analysis and recommendations.
REPORT_NARRATIVE_TOOL = {
    "name": "submit_report_narrative",
    "description": "Submit the narrative content for all report sections, including strategic recommendations.",
    "input_schema": {
        "type": "object",
        "properties": {
            "executive_summary": {
                "type": "string",
                "description": "2-3 paragraph C-suite overview with key metrics, critical gaps, and binding recommendation."
            },
            "policy_overview": {
                "type": "string",
                "description": "Policy declarations summary including carrier info, policy terms, limits, and retention."
            },
            "exclusion_analysis": {
                "type": "string",
                "description": "Analysis of all exclusions: standard, critical, and their severity with carve-backs."
            },
            "gap_analysis": {
                "type": "string",
                "description": "Coverage gaps organized by severity: Critical, Major, Moderate, Minor. Include potential exposure amounts."
            },
            "red_flag_summary": {
                "type": "string",
                "description": "Summary of all identified red flags with affected coverages and recommended mitigations."
            },
            "scenario_analysis": {
                "type": "string",
                "description": "4 loss scenarios (ransomware, data breach, BEC, dependent BI) with financial modeling."
            },
            "benchmarking_analysis": {
                "type": "string",
                "description": "Premium and coverage benchmarking against industry standards and peer group."
            },
            "policy_terms_analysis": {
                "type": "string",
                "description": "Analysis of claims handling, defense provisions, settlement, panel requirements, ERP, cancellation, M&A provisions."
            },
            "recommendations": {
                "type": "string",
                "description": "Prioritized recommendations: immediate (0-30 days), short-term (30-90 days), long-term (90+ days)."
            },
            "binding_recommendation": {
                "type": "string",
                "description": "Final binding recommendation with detailed rationale."
            },
            "policy_strengths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "6-10 bullet points of policy strengths for the Overall Assessment section. Each should be a concise statement with brief explanation."
            },
            "areas_for_enhancement": {
                "type": "array",
                "items": {"type": "string"},
                "description": "4-8 bullet points of areas for enhancement. Each should identify a specific gap with brief explanation."
            },
            "strategic_recommendations": {
                "type": "array",
                "description": "4-8 strategic recommendations with priority levels and budget impact estimates.",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Short title, e.g. 'Increase Data & Network Liability Limit'."},
                        "priority": {"type": "string", "enum": ["High", "Medium", "Low"], "description": "Priority level."},
                        "description": {"type": "string", "description": "2-3 sentence description of why this is important."},
                        "action": {"type": "string", "description": "Specific action to take."},
                        "budget_impact": {"type": "string", "description": "Estimated budget impact, e.g. 'Estimate $3,000-$8,000 additional premium'."},
                        "timeframe": {"type": "string", "enum": ["immediate", "medium_term"], "description": "Whether this is an immediate consideration or medium-term enhancement."},
                    },
                    "required": ["title", "priority", "description", "action", "budget_impact", "timeframe"],
                },
            },
            "risk_management_items": {
                "type": "array",
                "items": {"type": "string"},
                "description": "4-6 numbered risk management and loss control recommendations. Each should be a paragraph with title and detailed guidance."
            },
            "final_recommendation_detail": {
                "type": "string",
                "description": "Detailed final recommendation paragraph including: recommended action (e.g. 'Bind with Targeted Enhancements'), numbered list of critical/important/recommended items, budget impact summary, and value proposition statement."
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
    """Wrapper around the Anthropic SDK with streaming, retries, and structured outputs.

    Uses streaming API calls to avoid connection timeouts on long-running requests.
    The sandbox environment has a ~120s connection timeout that kills non-streaming calls.
    """

    def __init__(self):
        settings = get_settings()
        self.client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            max_retries=0,  # We handle retries ourselves for better logging
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
        """Make a streaming API call with exponential backoff retry.

        Uses streaming to keep the connection alive and avoid proxy timeouts.
        Returns a tuple of (response, usage_dict).
        """
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
        """Extract the tool use input from a response.

        If the response was truncated (stop_reason=max_tokens), attempts to
        recover partial JSON from the incomplete tool_use block.
        """
        for block in response.content:
            if block.type == "tool_use":
                return block.input

        # If stop_reason is max_tokens, try to recover partial JSON
        if response.stop_reason == "max_tokens":
            logger.warning(
                "Response truncated (max_tokens). Attempting partial JSON recovery."
            )
            for block in response.content:
                if block.type == "text":
                    text = block.text
                    # Look for the start of a JSON object in tool input
                    brace_start = text.find("{")
                    if brace_start >= 0:
                        partial_json = text[brace_start:]
                        recovered = self._try_recover_json(partial_json)
                        if recovered:
                            logger.info("Recovered partial JSON with %d top-level keys", len(recovered))
                            return recovered

        # Log what we got instead
        content_types = [block.type for block in response.content]
        logger.error("No tool_use block found. Got content types: %s, stop_reason: %s",
                      content_types, response.stop_reason)
        if response.content and response.content[0].type == "text":
            logger.error("Text content (first 500 chars): %s", response.content[0].text[:500])
        raise ValueError(f"No tool_use block found in response. Content types: {content_types}, stop_reason: {response.stop_reason}")

    def _try_recover_json(self, partial: str) -> dict | None:
        """Try to recover a valid JSON object from a truncated string.

        Attempts progressively more aggressive truncation to find a parseable subset.
        """
        # First, try as-is (maybe it's complete)
        try:
            return json.loads(partial)
        except json.JSONDecodeError:
            pass

        # Try closing open braces/brackets from the end
        # Find the last complete key-value pair
        for trim_chars in range(1, min(5000, len(partial))):
            candidate = partial[:-trim_chars]
            # Try to close it as an object
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
                        metadata_context: str) -> tuple[list[CoverageScore], list[CategorySummary], dict]:
        """Call 1: Score all coverage types with detailed per-coverage analysis.

        Returns:
            Tuple of (list of CoverageScore, list of CategorySummary, usage dict).
        """
        logger.info("Starting coverage scoring (Call 1) — using streaming")

        system = [{"type": "text", "text": self.system_prompt}]

        user_message = f"""Analyze the following cyber insurance policy and score ALL coverage types using the RhôneRisk 4-Tier Maturity Scoring System.

## Pre-Parsed Policy Metadata
{metadata_context}

## Full Policy Text
{policy_text}

{tables_text}

## Instructions
1. Score EVERY coverage type listed in the methodology (all 21 types across third-party, first-party, and cyber crime categories).
2. For coverages not explicitly found in the policy, score them as 0 (No Coverage).
3. For EACH coverage, provide:
   - The **limit** as stated in the policy (e.g. "$1,000,000 each Claim")
   - The **retention/deductible** (e.g. "$2,500")
   - A **detailed analysis paragraph** (3-6 sentences) explaining: what the coverage does, why the score was given, how the limit compares to industry standards, relevance to the client's specific industry, and any notable features or concerns
   - A specific **recommendation** if applicable (e.g. "Consider increasing to $2-3M if budget allows")
   - The correct **subcategory** for grouping (liability, incident_response, regulatory, business_interruption, extortion, ecrime, additional)
4. Identify ALL red flags per the red flag rules.
5. Evaluate each applicable scoring factor (limit adequacy, trigger mechanism, exclusions, etc.).
6. For each coverage category/subcategory group, provide a **category summary** with:
   - Average maturity score
   - A one-line assessment
   - 3-6 key findings (strengths, gaps, notable features)

The analysis paragraphs should read as a senior insurance analyst would write for a client-facing due diligence report. Be specific about dollar amounts, policy terms, and industry comparisons.

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
    ) -> tuple[ReportSections, list[StrategicRecommendation], dict]:
        """Call 2: Generate narrative content for all report sections via streaming.

        Uses 32K max_tokens to ensure the full narrative fits without truncation.

        Returns:
            Tuple of (ReportSections, list of StrategicRecommendation, usage dict).
        """
        logger.info("Starting report narrative generation (Call 2) — using streaming")

        system = [{"type": "text", "text": self.system_prompt}]

        user_message = f"""Generate the complete narrative content for a RhôneRisk cyber insurance policy analysis report.

## Client Information
{client_context}

## Pre-Parsed Policy Metadata
{metadata_context}

## Coverage Scores (from analysis)
{scores_context}

## Full Policy Text
{policy_text}

{tables_text}

## Instructions
Generate professional, detailed narrative content for each report section. The tone should be authoritative and analytical — written as a senior insurance analyst would for a client-facing deliverable.

**Required sections:**
1. **Executive Summary**: 2-3 paragraphs for C-suite audience with overall assessment and binding recommendation
2. **Policy Overview**: Declaration page details, carrier information, policy terms
3. **Exclusion Analysis**: Every exclusion identified with severity rating and carve-back assessment
4. **Gap Analysis**: All gaps organized by severity (Critical/Major/Moderate/Minor) with exposure estimates
5. **Red Flag Summary**: Summary of all identified red flags with affected coverages and mitigations
6. **Scenario Analysis**: 4 realistic loss scenarios with financial modeling against policy coverage
7. **Benchmarking Analysis**: Compare against industry standards for limits, premiums, and coverage breadth
8. **Policy Terms Analysis**: Claims handling, defense provisions, settlement, panel requirements, ERP
9. **Recommendations**: Prioritized by timeline (immediate/short-term/long-term) with cost-benefit reasoning
10. **Binding Recommendation**: Clear recommendation with detailed supporting rationale

**Required structured data:**
11. **Policy Strengths**: 6-10 concise bullet points highlighting the policy's strongest features
12. **Areas for Enhancement**: 4-8 bullet points identifying specific gaps or weaknesses
13. **Strategic Recommendations**: 4-8 detailed recommendations with priority (High/Medium/Low), specific actions, budget impact estimates, and timeframe (immediate vs medium-term)
14. **Risk Management Items**: 4-6 detailed risk management and loss control recommendations
15. **Final Recommendation Detail**: A comprehensive final recommendation paragraph with numbered action items, budget impact summary, and value proposition

Use the submit_report_narrative tool to return all section content."""

        messages = [{"role": "user", "content": user_message}]

        logger.info("Narrative call — system: %d chars, user: %d chars", len(self.system_prompt), len(user_message))

        response, usage = self._stream_with_retry(
            system=system,
            messages=messages,
            tools=[REPORT_NARRATIVE_TOOL],
            tool_choice={"type": "tool", "name": "submit_report_narrative"},
            max_tokens=32768,
        )

        result = self._extract_tool_input(response)

        # Extract strategic recommendations separately
        strategic_recs_raw = result.pop("strategic_recommendations", [])
        strategic_recs = [StrategicRecommendation(**sr) for sr in strategic_recs_raw]

        # Normalize list fields: Claude sometimes returns markdown strings instead of arrays
        list_fields = ["policy_strengths", "areas_for_enhancement", "risk_management_items"]
        for field in list_fields:
            val = result.get(field)
            if isinstance(val, str) and val.strip():
                # Split markdown bullet points into a list
                lines = []
                for line in val.split("\n"):
                    line = line.strip()
                    # Remove leading bullet markers: -, *, numbered (1., 2.), or bold markers
                    if line.startswith(("- ", "* ", "• ")):
                        line = line[2:].strip()
                    elif len(line) > 2 and line[0].isdigit() and "." in line[:4]:
                        # Handle "1. ", "2. ", etc.
                        dot_pos = line.index(".")
                        line = line[dot_pos + 1:].strip()
                    if line:
                        lines.append(line)
                result[field] = lines
                logger.info("Normalized '%s' from string to list with %d items", field, len(lines))
            elif val is None:
                result[field] = []

        # Remove any extra keys not in ReportSections to avoid Pydantic errors
        valid_fields = set(ReportSections.model_fields.keys())
        filtered_result = {k: v for k, v in result.items() if k in valid_fields}

        sections = ReportSections(**filtered_result)
        logger.info("Generated report narrative for %d sections, %d strategic recs in %.1fs",
                     sum(1 for v in filtered_result.values() if v), len(strategic_recs), usage["duration_seconds"])
        return sections, strategic_recs, usage

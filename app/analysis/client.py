"""Anthropic Claude API client with prompt caching, structured outputs, and retries."""

import json
import logging
import time
import traceback
from pathlib import Path

import anthropic

from app.config import get_settings
from app.models.scoring import CoverageScore, ReportSections

logger = logging.getLogger(__name__)

# Coverage score tool schema for structured output
COVERAGE_SCORES_TOOL = {
    "name": "submit_coverage_scores",
    "description": "Submit the complete set of coverage scores for the policy analysis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "coverage_scores": {
                "type": "array",
                "description": "Array of scores for each coverage type found in the policy.",
                "items": {
                    "type": "object",
                    "properties": {
                        "coverage_name": {
                            "type": "string",
                            "description": "Name of the coverage type being scored."
                        },
                        "coverage_category": {
                            "type": "string",
                            "enum": ["third_party", "first_party", "cyber_crime"],
                            "description": "Category this coverage belongs to."
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
                            "description": "Rating tier based on score."
                        },
                        "justification": {
                            "type": "string",
                            "description": "Detailed justification citing specific policy language."
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
                            "description": "Specific recommendations for improving this coverage."
                        },
                    },
                    "required": ["coverage_name", "coverage_category", "score", "rating", "justification", "red_flags"],
                },
            },
        },
        "required": ["coverage_scores"],
    },
}

# Report narrative tool schema
REPORT_NARRATIVE_TOOL = {
    "name": "submit_report_narrative",
    "description": "Submit the narrative content for all report sections.",
    "input_schema": {
        "type": "object",
        "properties": {
            "executive_summary": {"type": "string", "description": "2-3 paragraph C-suite overview with key metrics, critical gaps, and binding recommendation."},
            "policy_overview": {"type": "string", "description": "Policy declarations summary including carrier info, policy terms, limits, and retention."},
            "coverage_scoring_matrix": {"type": "string", "description": "Narrative analysis accompanying the coverage score table."},
            "third_party_analysis": {"type": "string", "description": "Detailed analysis of all third-party liability coverages."},
            "first_party_analysis": {"type": "string", "description": "Detailed analysis of all first-party coverages."},
            "cyber_crime_analysis": {"type": "string", "description": "Detailed analysis of all cyber crime coverages."},
            "policy_terms_analysis": {"type": "string", "description": "Analysis of claims handling, defense provisions, settlement, panel requirements, ERP, cancellation, M&A provisions."},
            "exclusion_analysis": {"type": "string", "description": "Analysis of all exclusions: standard, critical, and their severity with carve-backs."},
            "sublimit_analysis": {"type": "string", "description": "Analysis of all sublimits and their adequacy relative to coverage needs."},
            "gap_analysis": {"type": "string", "description": "Coverage gaps organized by severity: Critical, Major, Moderate, Minor. Include potential exposure amounts."},
            "red_flag_summary": {"type": "string", "description": "Summary of all identified red flags with affected coverages and recommended mitigations."},
            "msp_specific_analysis": {"type": "string", "description": "MSP/technology company specific analysis if applicable, or general industry considerations."},
            "regulatory_compliance": {"type": "string", "description": "GDPR, CCPA, HIPAA, GLBA, PCI-DSS, BIPA coverage alignment analysis."},
            "incident_response_evaluation": {"type": "string", "description": "Evaluation of incident response provisions, panel requirements, and breach cost coverage."},
            "business_interruption_analysis": {"type": "string", "description": "Detailed BI analysis: waiting periods, restoration periods, system failure vs cyber event triggers."},
            "social_engineering_analysis": {"type": "string", "description": "Social engineering, BEC, and funds transfer fraud coverage analysis with sublimit adequacy."},
            "vendor_dependency_analysis": {"type": "string", "description": "Dependent/contingent BI analysis, vendor coverage, cloud provider coverage assessment."},
            "benchmarking_analysis": {"type": "string", "description": "Premium and coverage benchmarking against industry standards and peer group."},
            "scenario_analysis": {"type": "string", "description": "4 loss scenarios (ransomware, data breach, BEC, dependent BI) with financial modeling."},
            "recommendations": {"type": "string", "description": "Prioritized recommendations: immediate (0-30 days), short-term (30-90 days), long-term (90+ days)."},
            "binding_recommendation": {"type": "string", "description": "Final binding recommendation with detailed rationale: Recommend Binding / Bind with Conditions / Require Major Modifications / Recommend Decline."},
        },
        "required": [
            "executive_summary", "policy_overview", "coverage_scoring_matrix",
            "third_party_analysis", "first_party_analysis", "cyber_crime_analysis",
            "policy_terms_analysis", "exclusion_analysis", "gap_analysis",
            "red_flag_summary", "recommendations", "binding_recommendation",
        ],
    },
}


class ClaudeClient:
    """Wrapper around the Anthropic SDK with caching, retries, and structured outputs."""

    def __init__(self):
        settings = get_settings()
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.claude_model
        self.max_tokens = settings.claude_max_tokens
        self.thinking_budget = settings.claude_thinking_budget
        self._system_prompt: str | None = None

    @property
    def system_prompt(self) -> str:
        if self._system_prompt is None:
            prompt_path = get_settings().knowledge_dir / "system_prompt.md"
            self._system_prompt = prompt_path.read_text()
            logger.info("Loaded system prompt: %d chars", len(self._system_prompt))
        return self._system_prompt

    def _call_with_retry(
        self,
        *,
        system: list[dict],
        messages: list[dict],
        tools: list[dict],
        tool_choice: dict,
        max_retries: int = 3,
    ) -> tuple[anthropic.types.Message, dict]:
        """Make an API call with exponential backoff retry.

        Returns a tuple of (response, usage_dict) where usage_dict contains
        input_tokens, output_tokens, and duration_seconds.
        """
        for attempt in range(max_retries):
            call_start = time.time()
            try:
                logger.info("Claude API call attempt %d/%d (model=%s, max_tokens=%d)",
                            attempt + 1, max_retries, self.model, self.max_tokens)
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=system,
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                )
                call_duration = time.time() - call_start
                usage = {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "duration_seconds": round(call_duration, 2),
                }
                logger.info(
                    "API call succeeded in %.1fs: %d input tokens, %d output tokens",
                    call_duration,
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                )
                return response, usage
            except anthropic.RateLimitError as e:
                call_duration = time.time() - call_start
                wait = 2 ** attempt * 5
                logger.warning("Rate limited after %.1fs, waiting %ds (attempt %d/%d): %s",
                               call_duration, wait, attempt + 1, max_retries, e)
                time.sleep(wait)
            except anthropic.APIConnectionError as e:
                call_duration = time.time() - call_start
                if attempt < max_retries - 1:
                    wait = 2 ** attempt * 3
                    logger.warning("Connection error after %.1fs, retrying in %ds (attempt %d/%d): %s",
                                   call_duration, wait, attempt + 1, max_retries, e)
                    time.sleep(wait)
                else:
                    logger.error("Connection error after %.1fs, all retries exhausted: %s\n%s",
                                 call_duration, e, traceback.format_exc())
                    raise
            except anthropic.APIStatusError as e:
                call_duration = time.time() - call_start
                if e.status_code >= 500 and attempt < max_retries - 1:
                    wait = 2 ** attempt * 2
                    logger.warning("Server error %d after %.1fs, retrying in %ds: %s",
                                   e.status_code, call_duration, wait, e)
                    time.sleep(wait)
                else:
                    logger.error("API error %d after %.1fs: %s\n%s",
                                 e.status_code, call_duration, e, traceback.format_exc())
                    raise
        raise RuntimeError("Max retries exceeded for Claude API call")

    def _extract_tool_input(self, response: anthropic.types.Message) -> dict:
        """Extract the tool use input from a response."""
        for block in response.content:
            if block.type == "tool_use":
                return block.input
        raise ValueError("No tool_use block found in response")

    def score_coverages(self, policy_text: str, tables_text: str,
                        metadata_context: str) -> tuple[list[CoverageScore], dict]:
        """Call 1: Score all coverage types in a single API call.

        Returns:
            Tuple of (list of CoverageScore objects, usage dict with token counts and duration).
        """
        logger.info("Starting coverage scoring (Call 1)")

        system = [
            {
                "type": "text",
                "text": self.system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        user_message = f"""Analyze the following cyber insurance policy and score ALL coverage types using the RhôneRisk 4-Tier Maturity Scoring System.

## Pre-Parsed Policy Metadata
{metadata_context}

## Full Policy Text
{policy_text}

{tables_text}

## Instructions
1. Score EVERY coverage type listed in the methodology (all 21 types across third-party, first-party, and cyber crime categories).
2. If a coverage type is not found in the policy, score it 0 with rating "No Coverage".
3. For each score, provide detailed justification citing specific policy language.
4. Identify ALL red flags per the red flag rules.
5. Evaluate each applicable scoring factor (limit adequacy, trigger mechanism, exclusions, etc.).
6. Provide specific, actionable recommendations for each coverage gap.

Use the submit_coverage_scores tool to return your complete analysis."""

        messages = [{"role": "user", "content": user_message}]

        response, usage = self._call_with_retry(
            system=system,
            messages=messages,
            tools=[COVERAGE_SCORES_TOOL],
            tool_choice={"type": "tool", "name": "submit_coverage_scores"},
        )

        result = self._extract_tool_input(response)
        scores = [CoverageScore(**s) for s in result["coverage_scores"]]
        logger.info("Scored %d coverage types", len(scores))
        return scores, usage

    def generate_report_narrative(
        self,
        policy_text: str,
        tables_text: str,
        metadata_context: str,
        scores_context: str,
        client_context: str,
    ) -> tuple[ReportSections, dict]:
        """Call 2: Generate narrative content for all 21 report sections.

        Returns:
            Tuple of (ReportSections, usage dict with token counts and duration).
        """
        logger.info("Starting report narrative generation (Call 2)")

        system = [
            {
                "type": "text",
                "text": self.system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        user_message = f"""Generate the complete narrative content for a RhôneRisk 21-section cyber insurance policy analysis report.

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
Generate professional, detailed narrative content for each report section. The tone should be authoritative and analytical — written as a senior insurance analyst would for a client-facing deliverable. Include:
1. **Executive Summary**: 2-3 paragraphs for C-suite audience with overall assessment and binding recommendation
2. **Policy Overview**: Declaration page details, carrier information, policy terms
3. **Coverage Analysis**: Detailed discussion of each coverage category with specific policy language citations
4. **Exclusion Analysis**: Every exclusion identified with severity rating and carve-back assessment
5. **Gap Analysis**: All gaps organized by severity (Critical/Major/Moderate/Minor) with exposure estimates
6. **Scenario Analysis**: 4 realistic loss scenarios with financial modeling against policy coverage
7. **Benchmarking**: Compare against industry standards for limits, premiums, and coverage breadth
8. **Recommendations**: Prioritized by timeline (immediate/short-term/long-term) with cost-benefit reasoning
9. **Binding Recommendation**: Clear recommendation with detailed supporting rationale

Use the submit_report_narrative tool to return all section content."""

        messages = [{"role": "user", "content": user_message}]

        response, usage = self._call_with_retry(
            system=system,
            messages=messages,
            tools=[REPORT_NARRATIVE_TOOL],
            tool_choice={"type": "tool", "name": "submit_report_narrative"},
        )

        result = self._extract_tool_input(response)
        sections = ReportSections(**result)
        logger.info("Generated report narrative for %d sections", sum(1 for v in result.values() if v))
        return sections, usage

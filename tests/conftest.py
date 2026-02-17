"""Test fixtures for RhôneRisk Policy Analyzer."""

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.config import Settings
from app.models.requests import ClientInfo
from app.models.scoring import (
    CoverageScore,
    PolicyAnalysis,
    PolicyMetadata,
    ReportSections,
    ScoringFactors,
)


@pytest.fixture
def settings(tmp_path):
    """Test settings with temp directory."""
    return Settings(
        anthropic_api_key="test-key",
        temp_dir=tmp_path / "temp",
        knowledge_dir=Path(__file__).parent.parent / "app" / "knowledge",
        templates_dir=Path(__file__).parent.parent / "templates",
    )


@pytest.fixture
def sample_policy_text():
    """Sample policy text for testing."""
    return """
# Cyber Insurance Policy

## Declarations

Policy Number: CYB-2026-001234
Named Insured: Acme Corporation
Carrier: Great American Insurance Company
Effective Date: 03/01/2026
Expiration Date: 03/01/2027
Aggregate Limit: $5,000,000
Per Occurrence Limit: $5,000,000
Deductible: $25,000
Annual Premium: $45,000
Retroactive Date: Full Prior Acts

## Coverage Part A - Third Party Liability

### Network Security Liability
Limit: $5,000,000 per claim / $5,000,000 aggregate
Deductible: $25,000
Coverage Trigger: Unauthorized access, denial of service, transmission of malicious code
Defense Costs: Outside limits
Payment Basis: Pay on behalf

### Privacy Liability
Limit: $5,000,000 per claim / $5,000,000 aggregate
Deductible: $25,000
Covers unauthorized disclosure of personally identifiable information.

## Coverage Part B - First Party

### Business Interruption
Waiting Period: 12 hours
Period of Restoration: 180 days
Limit: $2,000,000
Covers lost net income and extra expenses.

### Cyber Extortion
Limit: $5,000,000
Covers ransom payments, negotiation costs.
Cryptocurrency payments covered with carrier consent.

## Coverage Part C - Cyber Crime

### Social Engineering Fraud
Sublimit: $500,000
Verification: Callback verification required
Covers CEO impersonation, vendor impersonation, email compromise.

## Exclusions

1. War Exclusion: This policy does not cover loss arising from war, invasion, or hostile acts.
   Cyber terrorism carve-back: Covered.
2. Prior Known Acts: Standard exclusion for known circumstances.
3. Criminal Acts: Standard exclusion with final adjudication requirement.
4. Unencrypted Data: Exclusion applies only where encryption was feasible and not implemented.
"""


@pytest.fixture
def sample_metadata():
    """Sample parsed metadata."""
    return PolicyMetadata(
        policy_number="CYB-2026-001234",
        carrier_name="Great American Insurance Company",
        named_insured="Acme Corporation",
        effective_date="03/01/2026",
        expiration_date="03/01/2027",
        aggregate_limit="5,000,000",
        per_occurrence_limit="5,000,000",
        deductible="25,000",
        premium="45,000",
        retroactive_date="Full Prior Acts",
    )


@pytest.fixture
def sample_coverage_scores():
    """Sample coverage scores for testing post-processing."""
    return [
        CoverageScore(
            coverage_name="Network Security Liability",
            coverage_category="third_party",
            score=8,
            rating="Average",
            justification="Strong coverage with outside defense costs.",
            red_flags=[],
            scoring_factors=ScoringFactors(limit_adequacy=8, exclusion_scope=7),
        ),
        CoverageScore(
            coverage_name="Privacy Liability",
            coverage_category="third_party",
            score=7,
            rating="Average",
            justification="Good coverage for PII disclosure.",
            red_flags=[],
            scoring_factors=ScoringFactors(limit_adequacy=7, exclusion_scope=6),
        ),
        CoverageScore(
            coverage_name="Business Interruption - Cyber Event",
            coverage_category="first_party",
            score=7,
            rating="Average",
            justification="12-hour waiting period, 180-day restoration.",
            red_flags=[],
            scoring_factors=ScoringFactors(limit_adequacy=6, waiting_period=7),
        ),
        CoverageScore(
            coverage_name="Social Engineering Fraud",
            coverage_category="cyber_crime",
            score=5,
            rating="Average",
            justification="$500K sublimit on $5M aggregate (10%).",
            red_flags=["Social engineering sublimit <20% of aggregate"],
            scoring_factors=ScoringFactors(limit_adequacy=4, sublimit_analysis=3),
        ),
        CoverageScore(
            coverage_name="Cyber Extortion / Ransomware",
            coverage_category="first_party",
            score=8,
            rating="Average",
            justification="Full limits, crypto covered.",
            red_flags=[],
            scoring_factors=ScoringFactors(limit_adequacy=8),
        ),
    ]


@pytest.fixture
def sample_client_info():
    """Sample client information."""
    return ClientInfo(
        client_name="Acme Corporation",
        industry="Technology",
        annual_revenue="$50M",
        employee_count="250",
        is_msp=False,
    )


@pytest.fixture
def sample_analysis(sample_metadata, sample_coverage_scores):
    """Sample complete analysis for report generation testing."""
    return PolicyAnalysis(
        analysis_id="test123",
        status="completed",
        policy_metadata=sample_metadata,
        coverage_scores=sample_coverage_scores,
        overall_score=6.8,
        overall_rating="Average",
        binding_recommendation="Bind with Conditions",
        binding_rationale="Policy achieves a score of 6.8/10 with 1 red flag identified.",
        report_sections=ReportSections(
            executive_summary="This policy provides average coverage across most categories. Key concern is the low social engineering sublimit at 10% of aggregate.",
            policy_overview="The policy is issued by Great American Insurance Company with a $5M aggregate limit.",
            coverage_scoring_matrix="Coverage scores range from 5 to 8 across evaluated categories.",
            third_party_analysis="Third-party coverages are well-structured with outside defense costs.",
            first_party_analysis="First-party coverages are adequate with a 12-hour BI waiting period.",
            cyber_crime_analysis="Cyber crime coverage is limited by the low social engineering sublimit.",
            policy_terms_analysis="Claims-made policy with full prior acts coverage.",
            exclusion_analysis="War exclusion has a cyber terrorism carve-back. Unencrypted data exclusion is reasonable.",
            gap_analysis="Major gap: Social engineering sublimit at 10% of aggregate is below the 20% benchmark.",
            red_flag_summary="One red flag identified: Social engineering sublimit below 20% threshold.",
            recommendations="1. Increase social engineering sublimit to minimum $1M (20% of aggregate).",
            binding_recommendation="Recommend binding with condition to increase social engineering sublimit.",
        ),
        red_flag_count=1,
        critical_gaps=[],
    )

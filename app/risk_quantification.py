"""
RhôneRisk Cyber Risk Quantification Engine

Computes financial impact scenarios (Ransomware, Data Breach, BEC) using
deterministic formulas from the Cyber Risk Quantification Guide.
All dollar amounts are computed in Python — no LLM needed for the math.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Helper: parse revenue string → float
# ---------------------------------------------------------------------------

def parse_revenue(raw: str) -> float:
    """Convert strings like '$50M', '50000000', '$1.2B', '200K' → float."""
    if not raw:
        return 0.0
    s = raw.strip().replace(",", "").replace("$", "").upper()
    multiplier = 1.0
    if s.endswith("B"):
        multiplier = 1_000_000_000
        s = s[:-1]
    elif s.endswith("M"):
        multiplier = 1_000_000
        s = s[:-1]
    elif s.endswith("K"):
        multiplier = 1_000
        s = s[:-1]
    try:
        return float(s) * multiplier
    except ValueError:
        return 0.0


def parse_employee_count(raw: str) -> int:
    """Convert strings like '500', '1,200', '5K' → int."""
    if not raw:
        return 0
    s = raw.strip().replace(",", "").upper()
    multiplier = 1
    if s.endswith("K"):
        multiplier = 1000
        s = s[:-1]
    try:
        return int(float(s) * multiplier)
    except ValueError:
        return 0


def fmt_dollar(amount: float) -> str:
    """Format a dollar amount for display: $1,234,567"""
    if amount >= 1_000_000:
        return f"${amount:,.0f}"
    elif amount >= 1_000:
        return f"${amount:,.0f}"
    else:
        return f"${amount:,.2f}"


def fmt_pct(p: float) -> str:
    """Format a probability as percentage: 21.6%"""
    return f"{p * 100:.1f}%"


# ---------------------------------------------------------------------------
# Industry / size factor lookups
# ---------------------------------------------------------------------------

INDUSTRY_BASE_RATES = {
    # Annual probability base rates for each scenario
    # (ransomware, data_breach, bec)
    "healthcare":     (0.18, 0.12, 0.06),
    "financial":      (0.14, 0.10, 0.07),
    "financial services": (0.14, 0.10, 0.07),
    "manufacturing":  (0.15, 0.08, 0.05),
    "technology":     (0.12, 0.09, 0.05),
    "retail":         (0.13, 0.11, 0.06),
    "hospitality":    (0.13, 0.11, 0.06),
    "education":      (0.16, 0.10, 0.05),
    "government":     (0.14, 0.09, 0.04),
    "public entity":  (0.14, 0.09, 0.04),
    "energy":         (0.15, 0.08, 0.05),
    "professional services": (0.10, 0.07, 0.06),
    "legal":          (0.10, 0.08, 0.06),
    "default":        (0.12, 0.08, 0.05),
}

RANSOM_INDUSTRY_FACTOR = {
    "healthcare": 2.0,
    "financial": 1.8,
    "financial services": 1.8,
    "manufacturing": 1.5,
    "technology": 1.3,
    "energy": 1.5,
    "government": 1.2,
    "public entity": 1.2,
    "default": 1.0,
}


def _company_size_factor(revenue: float) -> float:
    """Size factor for probability calculations."""
    if revenue < 10_000_000:
        return 0.5
    elif revenue < 100_000_000:
        return 1.0
    elif revenue < 500_000_000:
        return 1.2
    elif revenue < 1_000_000_000:
        return 1.5
    else:
        return 2.0


def _ransom_size_factor(revenue: float) -> float:
    """Ransom payment size multiplier."""
    if revenue < 10_000_000:
        return 0.5
    elif revenue < 100_000_000:
        return 1.0
    elif revenue < 1_000_000_000:
        return 3.0
    else:
        return 10.0


def _estimated_records(employees: int, industry: str) -> int:
    """Rough estimate of PII / data records based on employees and industry."""
    ind = industry.lower().strip()
    if ind in ("healthcare", "financial", "financial services", "retail", "hospitality"):
        return max(employees * 200, 50_000)
    elif ind in ("technology", "education"):
        return max(employees * 150, 25_000)
    else:
        return max(employees * 100, 10_000)


# ---------------------------------------------------------------------------
# Scenario data classes
# ---------------------------------------------------------------------------

@dataclass
class ScenarioComponent:
    name: str
    amount: float
    detail: str = ""


@dataclass
class ScenarioResult:
    scenario_name: str
    description: str
    components: list[ScenarioComponent] = field(default_factory=list)
    total_loss: float = 0.0
    probability: float = 0.0
    expected_annual_loss: float = 0.0

    def compute_totals(self):
        self.total_loss = sum(c.amount for c in self.components)
        self.expected_annual_loss = self.total_loss * self.probability


@dataclass
class RiskQuantificationResult:
    scenarios: list[ScenarioResult] = field(default_factory=list)
    total_expected_annual_loss: float = 0.0
    total_worst_case: float = 0.0
    revenue: float = 0.0
    employees: int = 0
    industry: str = ""
    estimated_records: int = 0

    def compute_totals(self):
        self.total_expected_annual_loss = sum(s.expected_annual_loss for s in self.scenarios)
        self.total_worst_case = sum(s.total_loss for s in self.scenarios)


# ---------------------------------------------------------------------------
# Scenario calculators
# ---------------------------------------------------------------------------

def _calc_ransomware(revenue: float, employees: int, industry: str,
                     records: int, security_maturity: float = 1.0,
                     threat_interest: float = 1.0) -> ScenarioResult:
    """Ransomware scenario using the Risk Quantification Guide formulas."""
    ind = industry.lower().strip()
    rev_per_hour = revenue / 8760.0

    # 1. Business Interruption
    downtime_hours = 72 if revenue < 100_000_000 else 120
    impact_pct = 0.80
    bi_loss = rev_per_hour * downtime_hours * impact_pct
    extra_expenses = max(50_000, revenue * 0.003)
    total_bi = bi_loss + extra_expenses

    # 2. Ransom Payment
    base_ransom = 50_000
    size_f = _ransom_size_factor(revenue)
    ind_f = RANSOM_INDUSTRY_FACTOR.get(ind, RANSOM_INDUSTRY_FACTOR["default"])
    data_crit = 2.0 if ind in ("healthcare", "financial", "financial services") else 1.5
    ransom = base_ransom * size_f * ind_f * data_crit

    # 3. Recovery Costs
    systems = max(10, employees // 10)
    restoration = min(systems * 150 * 8, revenue * 0.01)  # IT hours × rate
    data_recovery = min(records * 0.05, revenue * 0.01)
    hardware = max(50_000, revenue * 0.001)
    software = max(25_000, revenue * 0.0005)
    total_recovery = restoration + data_recovery + hardware + software

    # 4. Incident Response
    forensics = max(80_000, revenue * 0.0015)
    legal = max(60_000, revenue * 0.001)
    pr = max(30_000, revenue * 0.0005)
    notifications = records * 1.0 if records < 100_000 else records * 0.50
    credit_monitoring = min(records, 100_000) * 120
    total_ir = forensics + legal + pr + notifications + credit_monitoring

    # 5. Reputational Impact
    churn_value = revenue * 0.02  # ~2% revenue impact
    acquisition_decline = revenue * 0.01
    total_rep = churn_value + acquisition_decline

    # Probability
    base_rates = INDUSTRY_BASE_RATES.get(ind, INDUSTRY_BASE_RATES["default"])
    prob = base_rates[0] * _company_size_factor(revenue) * security_maturity * threat_interest
    prob = min(prob, 0.50)  # cap at 50%

    scenario = ScenarioResult(
        scenario_name="Ransomware Attack",
        description=(
            f"A targeted ransomware attack encrypts critical systems, causing "
            f"{downtime_hours} hours of downtime affecting {impact_pct*100:.0f}% of operations. "
            f"Threat actors demand payment and threaten data exfiltration."
        ),
        components=[
            ScenarioComponent("Business Interruption", total_bi,
                              f"{downtime_hours}h downtime × {fmt_dollar(rev_per_hour)}/hr × {impact_pct*100:.0f}% + extra expenses"),
            ScenarioComponent("Ransom Payment", ransom,
                              f"Base {fmt_dollar(base_ransom)} × {size_f}x size × {ind_f}x industry × {data_crit}x data criticality"),
            ScenarioComponent("Recovery Costs", total_recovery,
                              f"System restoration + data recovery + hardware + software"),
            ScenarioComponent("Incident Response", total_ir,
                              f"Forensics + legal + PR + notifications + credit monitoring"),
            ScenarioComponent("Reputational Impact", total_rep,
                              f"Customer churn + acquisition decline (~3% revenue)"),
        ],
        probability=prob,
    )
    scenario.compute_totals()
    return scenario


def _calc_data_breach(revenue: float, employees: int, industry: str,
                      records: int, security_maturity: float = 1.0,
                      threat_interest: float = 1.2) -> ScenarioResult:
    """Large-scale data breach scenario."""
    ind = industry.lower().strip()
    breach_records = min(records, 500_000)  # assume up to 500K records exposed

    # 1. Detection & Containment
    siem_invest = max(15_000, revenue * 0.0003)
    ext_forensics = max(135_000, revenue * 0.002)
    containment = max(50_000, revenue * 0.001)
    total_dc = siem_invest + ext_forensics + containment

    # 2. Notification Costs
    letter_cost = breach_records * 0.20 * 0.75  # 20% get letters
    email_cost = breach_records * 0.80 * 0.05   # 80% get emails
    call_center = max(25_000, breach_records * 0.02 * 25)
    website = 25_000
    total_notif = letter_cost + email_cost + call_center + website

    # 3. Regulatory Fines
    if ind in ("healthcare",):
        base_fine = max(1_000_000, revenue * 0.02)
    elif ind in ("financial", "financial services"):
        base_fine = max(2_000_000, revenue * 0.03)
    else:
        base_fine = max(500_000, revenue * 0.01)
    severity = 0.5
    compliance_history = 1.0
    total_fines = base_fine * severity * compliance_history

    # 4. Legal & Litigation
    defense = max(500_000, revenue * 0.005)
    settlements = min(breach_records * 500, revenue * 0.10)
    class_action = 0.30 * min(breach_records * 1000, revenue * 0.20)
    total_legal = defense + settlements + class_action

    # 5. Business Impact
    customer_loss = revenue * 0.05  # 5% revenue from customer churn
    contract_penalties = revenue * 0.01
    competitive = revenue * 0.02
    total_biz = customer_loss + contract_penalties + competitive

    # Probability
    base_rates = INDUSTRY_BASE_RATES.get(ind, INDUSTRY_BASE_RATES["default"])
    prob = base_rates[1] * _company_size_factor(revenue) * security_maturity * threat_interest
    prob = min(prob, 0.40)

    scenario = ScenarioResult(
        scenario_name="Large-Scale Data Breach",
        description=(
            f"Unauthorized access exposes approximately {breach_records:,} records "
            f"containing PII/PHI, triggering regulatory notification requirements "
            f"and potential class-action litigation."
        ),
        components=[
            ScenarioComponent("Detection & Containment", total_dc,
                              "SIEM investigation + external forensics + containment"),
            ScenarioComponent("Notification Costs", total_notif,
                              f"{breach_records:,} records × notification costs"),
            ScenarioComponent("Regulatory Fines", total_fines,
                              f"Base fine × severity × compliance history"),
            ScenarioComponent("Legal & Litigation", total_legal,
                              "Defense costs + settlements + class action reserve"),
            ScenarioComponent("Business Impact", total_biz,
                              "Customer loss + contract penalties + competitive impact"),
        ],
        probability=prob,
    )
    scenario.compute_totals()
    return scenario


def _calc_bec(revenue: float, employees: int, industry: str,
              records: int, security_maturity: float = 0.7,
              threat_interest: float = 1.3) -> ScenarioResult:
    """Business Email Compromise scenario."""
    ind = industry.lower().strip()

    # 1. Direct Financial Loss
    # Scale with company size
    if revenue < 10_000_000:
        wire_fraud = 75_000
        vendor_redirect = 50_000
        payroll_diversion = 30_000
    elif revenue < 100_000_000:
        wire_fraud = 250_000
        vendor_redirect = 180_000
        payroll_diversion = 75_000
    elif revenue < 1_000_000_000:
        wire_fraud = 500_000
        vendor_redirect = 350_000
        payroll_diversion = 150_000
    else:
        wire_fraud = 1_000_000
        vendor_redirect = 500_000
        payroll_diversion = 250_000
    total_direct = wire_fraud + vendor_redirect + payroll_diversion

    # 2. Investigation
    internal = max(20_000, employees * 10)
    ext_forensics = max(32_000, revenue * 0.0005)
    legal_review = max(20_000, revenue * 0.0003)
    total_invest = internal + ext_forensics + legal_review

    # 3. Recovery Attempts (only 8% recovered)
    recovery_legal = max(50_000, total_direct * 0.08)
    asset_tracing = max(25_000, total_direct * 0.04)
    intl_legal = max(15_000, total_direct * 0.03)
    bank_fees = 5_000
    actual_recovery = total_direct * 0.08
    total_recovery = recovery_legal + asset_tracing + intl_legal + bank_fees - actual_recovery

    # 4. Business Disruption
    process_changes = max(25_000, revenue * 0.0003)
    new_controls = max(50_000, revenue * 0.0005)
    training = employees * 2 * 50  # 2 hours × $50/hr
    productivity = max(50_000, revenue * 0.001)
    total_disruption = process_changes + new_controls + training + productivity

    # 5. Third-Party Liability
    client_losses = total_direct * 0.35
    vendor_claims = vendor_redirect * 1.0
    contract_penalties = max(25_000, revenue * 0.0005)
    total_tp = client_losses + vendor_claims + contract_penalties

    # Probability
    base_rates = INDUSTRY_BASE_RATES.get(ind, INDUSTRY_BASE_RATES["default"])
    prob = base_rates[2] * _company_size_factor(revenue) * security_maturity * threat_interest
    prob = min(prob, 0.25)

    scenario = ScenarioResult(
        scenario_name="Business Email Compromise",
        description=(
            f"Sophisticated BEC attack compromises executive email accounts, "
            f"resulting in fraudulent wire transfers, vendor payment redirection, "
            f"and payroll diversion over a multi-week period."
        ),
        components=[
            ScenarioComponent("Direct Financial Loss", total_direct,
                              f"Wire fraud ({fmt_dollar(wire_fraud)}) + vendor redirect + payroll diversion"),
            ScenarioComponent("Investigation Costs", total_invest,
                              "Internal + external forensics + legal review"),
            ScenarioComponent("Recovery Attempts (net)", total_recovery,
                              f"Recovery costs minus {fmt_dollar(actual_recovery)} recovered (8% rate)"),
            ScenarioComponent("Business Disruption", total_disruption,
                              "Process changes + new controls + training + productivity loss"),
            ScenarioComponent("Third-Party Liability", total_tp,
                              "Client losses + vendor claims + contract penalties"),
        ],
        probability=prob,
    )
    scenario.compute_totals()
    return scenario


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_risk_quantification(
    revenue_str: str,
    employee_str: str,
    industry: str,
    security_maturity: float = 1.0,  # 0.3 (excellent) to 3.0 (poor)
    threat_interest: float = 1.0,    # 0.5 (low) to 2.0 (high)
) -> RiskQuantificationResult:
    """
    Main entry point. Computes all three risk scenarios and returns
    a RiskQuantificationResult with pre-computed dollar amounts.
    """
    revenue = parse_revenue(revenue_str)
    employees = parse_employee_count(employee_str)
    ind = industry.lower().strip() if industry else "default"
    records = _estimated_records(employees, ind)

    # If we have no revenue data, use a reasonable default
    if revenue <= 0:
        revenue = 50_000_000  # default $50M

    if employees <= 0:
        employees = 250  # default

    result = RiskQuantificationResult(
        revenue=revenue,
        employees=employees,
        industry=industry or "General",
        estimated_records=records,
    )

    result.scenarios = [
        _calc_ransomware(revenue, employees, ind, records, security_maturity, threat_interest),
        _calc_data_breach(revenue, employees, ind, records, security_maturity, threat_interest),
        _calc_bec(revenue, employees, ind, records, security_maturity, threat_interest),
    ]

    result.compute_totals()
    return result


def risk_quantification_to_markdown(rq: RiskQuantificationResult) -> str:
    """
    Render the risk quantification result as Markdown text that can be
    injected into the report narrative or used as context for Claude.
    """
    lines = []
    lines.append("## Risk Quantification & Financial Modeling\n")
    lines.append(f"**Company Profile:** {rq.industry} | Revenue: {fmt_dollar(rq.revenue)} | "
                 f"Employees: {rq.employees:,} | Estimated Records: {rq.estimated_records:,}\n")

    lines.append("### Scenario Analysis\n")

    for i, s in enumerate(rq.scenarios, 1):
        lines.append(f"#### Scenario {i}: {s.scenario_name}")
        lines.append(f"**Description:** {s.description}\n")
        lines.append("| Component | Amount | Detail |")
        lines.append("|-----------|--------|--------|")
        for c in s.components:
            lines.append(f"| {c.name} | {fmt_dollar(c.amount)} | {c.detail} |")
        lines.append(f"| **Total Estimated Loss** | **{fmt_dollar(s.total_loss)}** | |")
        lines.append(f"\n- **Annual Probability:** {fmt_pct(s.probability)}")
        lines.append(f"- **Expected Annual Loss:** {fmt_dollar(s.expected_annual_loss)}\n")

    lines.append("### Total Risk Exposure Summary\n")
    lines.append("| Metric | Amount |")
    lines.append("|--------|--------|")
    lines.append(f"| Total Worst-Case Exposure (all scenarios) | {fmt_dollar(rq.total_worst_case)} |")
    lines.append(f"| Total Expected Annual Loss (EAL) | {fmt_dollar(rq.total_expected_annual_loss)} |")
    for s in rq.scenarios:
        lines.append(f"| {s.scenario_name} EAL | {fmt_dollar(s.expected_annual_loss)} |")
    lines.append("")

    return "\n".join(lines)


def risk_quantification_to_dict(rq: RiskQuantificationResult) -> dict:
    """Convert to a dict suitable for JSON serialization or template rendering."""
    return {
        "company_profile": {
            "industry": rq.industry,
            "revenue": fmt_dollar(rq.revenue),
            "revenue_raw": rq.revenue,
            "employees": rq.employees,
            "estimated_records": rq.estimated_records,
        },
        "scenarios": [
            {
                "name": s.scenario_name,
                "description": s.description,
                "components": [
                    {"name": c.name, "amount": c.amount, "amount_fmt": fmt_dollar(c.amount), "detail": c.detail}
                    for c in s.components
                ],
                "total_loss": s.total_loss,
                "total_loss_fmt": fmt_dollar(s.total_loss),
                "probability": s.probability,
                "probability_fmt": fmt_pct(s.probability),
                "expected_annual_loss": s.expected_annual_loss,
                "eal_fmt": fmt_dollar(s.expected_annual_loss),
            }
            for s in rq.scenarios
        ],
        "summary": {
            "total_worst_case": rq.total_worst_case,
            "total_worst_case_fmt": fmt_dollar(rq.total_worst_case),
            "total_eal": rq.total_expected_annual_loss,
            "total_eal_fmt": fmt_dollar(rq.total_expected_annual_loss),
        },
    }


def risk_quantification_to_html(rq: RiskQuantificationResult) -> str:
    """
    Render the risk quantification result as HTML suitable for embedding
    in the PDF report template.
    """
    html_parts = []
    html_parts.append('<div class="risk-quantification">')
    html_parts.append(f'<p><strong>Company Profile:</strong> {rq.industry} | '
                      f'Revenue: {fmt_dollar(rq.revenue)} | '
                      f'Employees: {rq.employees:,} | '
                      f'Estimated Records: {rq.estimated_records:,}</p>')

    for i, s in enumerate(rq.scenarios, 1):
        html_parts.append(f'<h4>Scenario {i}: {s.scenario_name}</h4>')
        html_parts.append(f'<p><em>{s.description}</em></p>')
        html_parts.append('<table class="data-table">')
        html_parts.append('<thead><tr><th>Component</th><th>Amount</th><th>Detail</th></tr></thead>')
        html_parts.append('<tbody>')
        for c in s.components:
            html_parts.append(f'<tr><td>{c.name}</td><td>{fmt_dollar(c.amount)}</td><td>{c.detail}</td></tr>')
        html_parts.append(f'<tr class="total-row"><td><strong>Total Estimated Loss</strong></td>'
                          f'<td><strong>{fmt_dollar(s.total_loss)}</strong></td><td></td></tr>')
        html_parts.append('</tbody></table>')
        html_parts.append(f'<p><strong>Annual Probability:</strong> {fmt_pct(s.probability)} &nbsp;|&nbsp; '
                          f'<strong>Expected Annual Loss:</strong> {fmt_dollar(s.expected_annual_loss)}</p>')

    html_parts.append('<h4>Total Risk Exposure Summary</h4>')
    html_parts.append('<table class="data-table">')
    html_parts.append('<thead><tr><th>Metric</th><th>Amount</th></tr></thead>')
    html_parts.append('<tbody>')
    html_parts.append(f'<tr><td>Total Worst-Case Exposure (all scenarios)</td>'
                      f'<td><strong>{fmt_dollar(rq.total_worst_case)}</strong></td></tr>')
    html_parts.append(f'<tr><td>Total Expected Annual Loss (EAL)</td>'
                      f'<td><strong>{fmt_dollar(rq.total_expected_annual_loss)}</strong></td></tr>')
    for s in rq.scenarios:
        html_parts.append(f'<tr><td>{s.scenario_name} EAL</td><td>{fmt_dollar(s.expected_annual_loss)}</td></tr>')
    html_parts.append('</tbody></table>')
    html_parts.append('</div>')

    return "\n".join(html_parts)

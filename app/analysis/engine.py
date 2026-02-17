"""Analysis engine: orchestrates the full policy analysis pipeline."""

import logging
import uuid
from datetime import datetime
from pathlib import Path

from app.analysis.client import ClaudeClient
from app.analysis.prompts import (
    format_client_context,
    format_metadata_context,
    format_scores_context,
)
from app.analysis.postprocess import (
    apply_red_flag_penalties,
    calculate_overall_score,
    determine_binding_recommendation,
)
from app.etl.extractor import extract_policy, format_tables_for_context
from app.etl.parser import parse_metadata
from app.models.requests import ClientInfo
from app.models.scoring import PolicyAnalysis, PolicyMetadata, ReportSections
from app.report.generator import generate_pdf_report

logger = logging.getLogger(__name__)


class AnalysisEngine:
    """Orchestrates the end-to-end policy analysis pipeline."""

    def __init__(self):
        self.claude = ClaudeClient()

    def analyze_policy(
        self,
        pdf_path: Path,
        client_info: ClientInfo | None = None,
        output_dir: Path | None = None,
    ) -> PolicyAnalysis:
        """Run the complete analysis pipeline on a policy PDF.

        Pipeline stages:
        1. EXTRACT - PDF to markdown + tables
        2. PARSE - Extract structured metadata
        3. ANALYZE (Call 1) - Score all coverages
        4. POST-PROCESS - Apply red flag penalties, calculate overall score
        5. ANALYZE (Call 2) - Generate report narrative
        6. GENERATE - Create branded PDF report

        Args:
            pdf_path: Path to the policy PDF file.
            client_info: Optional client metadata.
            output_dir: Directory for generated report PDF. Defaults to temp dir.

        Returns:
            Complete PolicyAnalysis with scores, narrative, and report path.
        """
        analysis_id = uuid.uuid4().hex[:12]
        client_info = client_info or ClientInfo()

        logger.info("Starting analysis %s for %s", analysis_id, pdf_path.name)

        # Step 1: EXTRACT
        logger.info("[%s] Step 1: Extracting PDF", analysis_id)
        md_text, tables = extract_policy(pdf_path)
        tables_text = format_tables_for_context(tables)
        logger.info("[%s] Extracted %d chars, %d tables", analysis_id, len(md_text), len(tables))

        # Step 2: PARSE
        logger.info("[%s] Step 2: Parsing metadata", analysis_id)
        metadata = parse_metadata(md_text)
        metadata_context = format_metadata_context(metadata)

        # Step 3: ANALYZE - Call 1 (Coverage Scoring)
        logger.info("[%s] Step 3: Scoring coverages (API Call 1)", analysis_id)
        coverage_scores = self.claude.score_coverages(
            policy_text=md_text,
            tables_text=tables_text,
            metadata_context=metadata_context,
        )

        # Step 4: POST-PROCESS
        logger.info("[%s] Step 4: Post-processing scores", analysis_id)
        coverage_scores = apply_red_flag_penalties(coverage_scores)
        overall_score, overall_rating = calculate_overall_score(coverage_scores)

        # Collect red flags and critical gaps
        all_red_flags = []
        critical_gaps = []
        for s in coverage_scores:
            all_red_flags.extend(s.red_flags)
            if s.score <= 1:
                critical_gaps.append(f"{s.coverage_name}: {s.rating} ({s.score}/10)")

        red_flag_count = len(set(all_red_flags))
        binding_rec, binding_rationale = determine_binding_recommendation(
            overall_score, red_flag_count, critical_gaps,
        )

        # Step 5: ANALYZE - Call 2 (Report Narrative)
        logger.info("[%s] Step 5: Generating report narrative (API Call 2)", analysis_id)
        client_context = format_client_context(client_info)
        scores_context = format_scores_context(coverage_scores)

        report_sections = self.claude.generate_report_narrative(
            policy_text=md_text,
            tables_text=tables_text,
            metadata_context=metadata_context,
            scores_context=scores_context,
            client_context=client_context,
        )

        # Step 6: GENERATE PDF Report
        logger.info("[%s] Step 6: Generating PDF report", analysis_id)
        analysis = PolicyAnalysis(
            analysis_id=analysis_id,
            status="completed",
            policy_metadata=metadata,
            coverage_scores=coverage_scores,
            overall_score=overall_score,
            overall_rating=overall_rating,
            binding_recommendation=binding_rec,
            binding_rationale=binding_rationale,
            report_sections=report_sections,
            red_flag_count=red_flag_count,
            critical_gaps=critical_gaps,
        )

        if output_dir is None:
            from app.config import get_settings
            output_dir = get_settings().temp_dir / "reports"
        output_dir.mkdir(parents=True, exist_ok=True)

        client_name = client_info.client_name or metadata.named_insured or "Unknown"
        safe_name = "".join(c if c.isalnum() or c in "-_ " else "" for c in client_name).strip()
        date_str = datetime.now().strftime("%Y%m%d")
        pdf_filename = f"RhoneRisk_Analysis_{safe_name}_{date_str}.pdf"
        pdf_path_out = output_dir / pdf_filename

        generate_pdf_report(analysis, pdf_path_out)
        logger.info("[%s] Analysis complete. Report: %s", analysis_id, pdf_path_out)

        return analysis

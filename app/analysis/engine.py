"""Analysis engine: orchestrates the full policy analysis pipeline."""

import logging
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

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
from app.monitoring import AnalysisRecord
from app.report.generator import generate_pdf_report

logger = logging.getLogger(__name__)

# Type alias for progress callback: (status: str, progress: int) -> None
ProgressCallback = Callable[[str, int], None]


class AnalysisEngine:
    """Orchestrates the end-to-end policy analysis pipeline."""

    def __init__(self):
        self.claude = ClaudeClient()

    def analyze_policy(
        self,
        pdf_path: Path,
        client_info: ClientInfo | None = None,
        output_dir: Path | None = None,
        progress_callback: Optional[ProgressCallback] = None,
        record: Optional[AnalysisRecord] = None,
    ) -> PolicyAnalysis:
        """Run the complete analysis pipeline on a policy PDF.

        Pipeline stages:
        1. EXTRACT - PDF to markdown + tables
        2. PARSE - Extract structured metadata
        3. ANALYZE (Call 1) - Score all coverages with detailed analysis
        4. POST-PROCESS - Apply red flag penalties, calculate overall score
        5. ANALYZE (Call 2) - Generate report narrative with strategic recs
        6. GENERATE - Create branded PDF report

        Args:
            pdf_path: Path to the policy PDF file.
            client_info: Optional client metadata.
            output_dir: Directory for generated report PDF. Defaults to temp dir.
            progress_callback: Optional callback invoked at each pipeline stage
                with (status_string, progress_percentage).
            record: Optional AnalysisRecord for monitoring/timing.

        Returns:
            Complete PolicyAnalysis with scores, narrative, and report path.
        """
        analysis_id = uuid.uuid4().hex[:12]
        client_info = client_info or ClientInfo()

        def _report_progress(status: str, progress: int) -> None:
            """Report progress via callback if provided."""
            if progress_callback:
                try:
                    progress_callback(status, progress)
                except Exception as e:
                    logger.warning("Progress callback failed: %s", e)

        def _log(level: str, stage: str, msg: str) -> None:
            """Log to both Python logger and monitoring record."""
            getattr(logger, level.lower(), logger.info)(msg)
            if record:
                record.add_log(level, stage, msg)

        _log("INFO", "pipeline", f"Starting analysis {analysis_id} for {pdf_path.name}")
        if record:
            record.mark_started()

        # Step 1: EXTRACT
        _log("INFO", "extracting", f"[{analysis_id}] Step 1: Extracting PDF")
        if record:
            record.start_stage("extracting")
        _report_progress("extracting", 15)

        try:
            md_text, tables = extract_policy(pdf_path)
            tables_text = format_tables_for_context(tables)
        except Exception as e:
            _log("ERROR", "extracting", f"PDF extraction failed: {e}\n{traceback.format_exc()}")
            raise

        _log("INFO", "extracting", f"[{analysis_id}] Extracted {len(md_text)} chars, {len(tables)} tables")

        # Try to get page count
        try:
            import pdfplumber
            with pdfplumber.open(pdf_path) as pdf:
                page_count = len(pdf.pages)
                if record:
                    record.page_count = page_count
                _log("INFO", "extracting", f"[{analysis_id}] PDF has {page_count} pages")
        except Exception:
            pass

        if record:
            record.end_stage("extracting")

        # Step 2: PARSE
        _log("INFO", "parsing", f"[{analysis_id}] Step 2: Parsing metadata")
        if record:
            record.start_stage("parsing")
        _report_progress("parsing", 25)

        try:
            metadata = parse_metadata(md_text)
            metadata_context = format_metadata_context(metadata)
        except Exception as e:
            _log("ERROR", "parsing", f"Metadata parsing failed: {e}\n{traceback.format_exc()}")
            raise

        if record:
            record.end_stage("parsing")

        # Step 3: ANALYZE - Call 1 (Coverage Scoring with detailed analysis)
        _log("INFO", "scoring", f"[{analysis_id}] Step 3: Scoring coverages with detailed analysis (API Call 1)")
        if record:
            record.start_stage("scoring")
        _report_progress("scoring", 35)

        try:
            coverage_scores, category_summaries, scoring_usage = self.claude.score_coverages(
                policy_text=md_text,
                tables_text=tables_text,
                metadata_context=metadata_context,
            )
            if record and scoring_usage:
                record.scoring_input_tokens = scoring_usage.get("input_tokens", 0)
                record.scoring_output_tokens = scoring_usage.get("output_tokens", 0)
                _log("INFO", "scoring",
                     f"[{analysis_id}] Scoring API: {scoring_usage.get('input_tokens', 0)} input, "
                     f"{scoring_usage.get('output_tokens', 0)} output tokens, "
                     f"{scoring_usage.get('duration_seconds', 0):.1f}s")
        except Exception as e:
            _log("ERROR", "scoring", f"Coverage scoring failed: {e}\n{traceback.format_exc()}")
            raise

        _log("INFO", "scoring",
             f"[{analysis_id}] Scored {len(coverage_scores)} coverages, {len(category_summaries)} category summaries")
        _report_progress("scoring", 50)
        if record:
            record.end_stage("scoring")

        # Step 4: POST-PROCESS
        _log("INFO", "post_processing", f"[{analysis_id}] Step 4: Post-processing scores")
        if record:
            record.start_stage("post_processing")
        _report_progress("post_processing", 60)

        try:
            coverage_scores = apply_red_flag_penalties(coverage_scores)
            overall_score, overall_rating = calculate_overall_score(coverage_scores)

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
            _log("INFO", "post_processing",
                 f"[{analysis_id}] Score: {overall_score:.1f} ({overall_rating}), "
                 f"{red_flag_count} red flags, {len(critical_gaps)} critical gaps, "
                 f"Recommendation: {binding_rec}")
        except Exception as e:
            _log("ERROR", "post_processing", f"Post-processing failed: {e}\n{traceback.format_exc()}")
            raise

        if record:
            record.end_stage("post_processing")

        # Step 5: ANALYZE - Call 2 (Report Narrative with strategic recs)
        _log("INFO", "generating_narrative", f"[{analysis_id}] Step 5: Generating report narrative (API Call 2)")
        if record:
            record.start_stage("generating_narrative")
        _report_progress("generating_narrative", 70)

        try:
            client_context = format_client_context(client_info)
            scores_context = format_scores_context(coverage_scores)

            report_sections, strategic_recs, narrative_usage = self.claude.generate_report_narrative(
                policy_text=md_text,
                tables_text=tables_text,
                metadata_context=metadata_context,
                scores_context=scores_context,
                client_context=client_context,
            )
            if record and narrative_usage:
                record.narrative_input_tokens = narrative_usage.get("input_tokens", 0)
                record.narrative_output_tokens = narrative_usage.get("output_tokens", 0)
                _log("INFO", "generating_narrative",
                     f"[{analysis_id}] Narrative API: {narrative_usage.get('input_tokens', 0)} input, "
                     f"{narrative_usage.get('output_tokens', 0)} output tokens, "
                     f"{narrative_usage.get('duration_seconds', 0):.1f}s")
        except Exception as e:
            _log("ERROR", "generating_narrative", f"Narrative generation failed: {e}\n{traceback.format_exc()}")
            raise

        _report_progress("generating_narrative", 80)
        if record:
            record.end_stage("generating_narrative")

        # Step 6: GENERATE PDF Report
        _log("INFO", "generating_report", f"[{analysis_id}] Step 6: Generating PDF report")
        if record:
            record.start_stage("generating_report")
        _report_progress("generating_report", 90)

        try:
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
                category_summaries=category_summaries,
                strategic_recommendations=strategic_recs,
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
            report_size = pdf_path_out.stat().st_size / 1024
            _log("INFO", "generating_report",
                 f"[{analysis_id}] Report generated: {pdf_filename} ({report_size:.0f} KB)")
        except Exception as e:
            _log("ERROR", "generating_report", f"PDF report generation failed: {e}\n{traceback.format_exc()}")
            raise

        if record:
            record.end_stage("generating_report")
            record.mark_completed()

        _report_progress("completed", 100)

        return analysis

"""Report generation: Jinja2 HTML rendering + WeasyPrint PDF conversion."""

import logging
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from markupsafe import Markup, escape
from jinja2 import Environment, FileSystemLoader

from app.config import get_settings

logger = logging.getLogger(__name__)


def _get_jinja_env() -> Environment:
    """Create a Jinja2 environment with the templates directory."""
    settings = get_settings()
    return Environment(
        loader=FileSystemLoader(str(settings.templates_dir)),
        autoescape=True,
    )


def _score_color(score: int) -> str:
    """Return a CSS color class for a score value."""
    if score >= 9:
        return "score-superior"
    elif score >= 5:
        return "score-average"
    elif score >= 2:
        return "score-basic"
    else:
        return "score-nocoverage"


def _md_to_html(text: str) -> Markup:
    """Convert markdown-style text to safe HTML paragraphs.

    Handles:
    - Double newlines -> paragraph breaks
    - Single newlines -> <br>
    - **bold** -> <strong>
    - Strips literal <br> tags that Claude sometimes includes
    """
    if not text:
        return Markup("")
    # Escape HTML entities first for safety
    safe_text = str(escape(text))
    # Remove literal <br> and <br/> tags that Claude sometimes embeds
    safe_text = safe_text.replace("&lt;br&gt;", "\n").replace("&lt;br/&gt;", "\n").replace("&lt;br /&gt;", "\n")
    # Convert **bold** to <strong>
    import re
    safe_text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', safe_text)
    # Convert double newlines to paragraph breaks
    paragraphs = safe_text.split("\n\n")
    if len(paragraphs) > 1:
        result = "".join(f"<p>{p.strip()}</p>" for p in paragraphs if p.strip())
    else:
        # Single block — just convert newlines to <br>
        result = safe_text.replace("\n", "<br>")
    return Markup(result)


def _rating_badge_class(rating: str) -> str:
    """Return a CSS class for a rating badge."""
    mapping = {
        "Superior": "badge-superior",
        "Average": "badge-average",
        "Basic": "badge-basic",
        "No Coverage": "badge-none",
    }
    return mapping.get(rating, "badge-none")


def render_html_report(analysis) -> str:
    """Render the analysis results into an HTML report.

    Args:
        analysis: PolicyAnalysis object with all scores and narrative.

    Returns:
        HTML string of the complete report.
    """
    env = _get_jinja_env()
    env.filters["md_to_html"] = _md_to_html
    env.globals["score_color"] = _score_color
    env.globals["rating_badge_class"] = _rating_badge_class
    env.globals["now"] = datetime.now()

    template = env.get_template("report.html.j2")

    # Organize scores by top-level category
    third_party = [s for s in analysis.coverage_scores if s.coverage_category == "third_party"]
    first_party = [s for s in analysis.coverage_scores if s.coverage_category == "first_party"]
    cyber_crime = [s for s in analysis.coverage_scores if s.coverage_category == "cyber_crime"]

    # Group first-party scores by subcategory for the template
    first_party_by_subcat = defaultdict(list)
    for s in first_party:
        subcat = s.coverage_subcategory or "additional"
        first_party_by_subcat[subcat].append(s)

    # Build a map of category_key -> CategorySummary for easy template lookup
    category_summaries_map = {}
    for cs in (analysis.category_summaries or []):
        category_summaries_map[cs.category_key] = cs

    html = template.render(
        analysis=analysis,
        metadata=analysis.policy_metadata,
        sections=analysis.report_sections,
        scores=analysis.coverage_scores,
        third_party_scores=third_party,
        first_party_scores=first_party,
        cyber_crime_scores=cyber_crime,
        first_party_by_subcat=dict(first_party_by_subcat),
        category_summaries=analysis.category_summaries or [],
        category_summaries_map=category_summaries_map,
        strategic_recommendations=analysis.strategic_recommendations or [],
        overall_score=analysis.overall_score,
        overall_rating=analysis.overall_rating,
        binding_recommendation=analysis.binding_recommendation,
        binding_rationale=analysis.binding_rationale,
        red_flag_count=analysis.red_flag_count,
        critical_gaps=analysis.critical_gaps,
        generation_date=datetime.now().strftime("%B %d, %Y"),
    )

    return html


def generate_pdf_report(analysis, output_path: Path) -> Path:
    """Generate a branded PDF report from the analysis results.

    Args:
        analysis: PolicyAnalysis object.
        output_path: Path to write the PDF file.

    Returns:
        Path to the generated PDF.
    """
    from weasyprint import HTML

    logger.info("Rendering HTML report")
    html_content = render_html_report(analysis)

    logger.info("Converting HTML to PDF: %s", output_path)
    settings = get_settings()
    base_url = str(settings.templates_dir)

    HTML(string=html_content, base_url=base_url).write_pdf(str(output_path))

    logger.info("PDF generated: %s (%.1f KB)", output_path, output_path.stat().st_size / 1024)
    return output_path

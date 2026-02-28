"""Report generation: Jinja2 HTML rendering + WeasyPrint PDF conversion."""

import logging
import re
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
    """Convert markdown-style text to safe HTML.

    Handles:
    - Markdown tables -> HTML <table>
    - Double newlines -> paragraph breaks
    - Single newlines -> <br>
    - **bold** -> <strong>
    - ### headings -> <h3>, ## -> <h2>
    - - bullet lists -> <ul><li>
    """
    if not text:
        return Markup("")

    # Escape HTML entities first for safety
    safe_text = str(escape(text))
    # Remove literal <br> tags that Claude sometimes embeds
    safe_text = safe_text.replace("&lt;br&gt;", "\n").replace("&lt;br/&gt;", "\n").replace("&lt;br /&gt;", "\n")

    # Split into blocks by double newlines
    blocks = re.split(r'\n\n+', safe_text)
    html_parts = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.split("\n")

        # Check if this block is a markdown table
        if _is_markdown_table(lines):
            html_parts.append(_render_markdown_table(lines))
            continue

        # Check if this block is a bullet list
        if all(line.strip().startswith(("- ", "* ", "• ")) or not line.strip() for line in lines if line.strip()):
            items = []
            for line in lines:
                line = line.strip()
                if line.startswith(("- ", "* ", "• ")):
                    item = line[2:].strip()
                    # Convert **bold** to <strong>
                    item = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', item)
                    items.append(f"<li>{item}</li>")
            if items:
                html_parts.append(f"<ul>{''.join(items)}</ul>")
            continue

        # Check if this block is a heading
        if lines[0].startswith("### "):
            heading_text = lines[0][4:].strip()
            heading_text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', heading_text)
            html_parts.append(f"<h3>{heading_text}</h3>")
            if len(lines) > 1:
                rest = "\n".join(lines[1:])
                rest = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', rest)
                html_parts.append(f"<p>{rest.replace(chr(10), '<br>')}</p>")
            continue
        elif lines[0].startswith("## "):
            heading_text = lines[0][3:].strip()
            heading_text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', heading_text)
            html_parts.append(f"<h2>{heading_text}</h2>")
            if len(lines) > 1:
                rest = "\n".join(lines[1:])
                rest = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', rest)
                html_parts.append(f"<p>{rest.replace(chr(10), '<br>')}</p>")
            continue

        # Regular paragraph
        paragraph = block.replace("\n", "<br>")
        paragraph = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', paragraph)
        html_parts.append(f"<p>{paragraph}</p>")

    return Markup("".join(html_parts))


def _is_markdown_table(lines: list[str]) -> bool:
    """Check if a set of lines form a markdown table."""
    if len(lines) < 2:
        return False
    # A markdown table has | delimiters and a separator row with ---
    has_pipes = sum(1 for line in lines if "|" in line) >= 2
    has_separator = any(re.match(r'^[\s|:-]+$', line) and "---" in line for line in lines)
    return has_pipes and has_separator


def _render_markdown_table(lines: list[str]) -> str:
    """Convert markdown table lines to an HTML table."""
    rows = []
    is_header = True

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip separator row
        if re.match(r'^[\s|:-]+$', line) and "---" in line:
            is_header = False
            continue

        # Parse cells
        cells = [c.strip() for c in line.split("|")]
        # Remove empty first/last cells from leading/trailing pipes
        if cells and not cells[0]:
            cells = cells[1:]
        if cells and not cells[-1]:
            cells = cells[:-1]

        tag = "th" if is_header else "td"
        bold_pattern = re.compile(r'[*][*](.+?)[*][*]')
        processed_cells = [bold_pattern.sub(r'<strong>\1</strong>', cell) for cell in cells]
        row_html = "".join(
            f"<{tag}>{cell_html}</{tag}>"
            for cell_html in processed_cells
        )
        rows.append(f"<tr>{row_html}</tr>")

    if not rows:
        return ""

    # First row is header
    header = rows[0]
    body = "".join(rows[1:])
    return f"<table><thead>{header}</thead><tbody>{body}</tbody></table>"


def _rating_badge_class(rating: str) -> str:
    """Return a CSS class for a rating badge."""
    mapping = {
        "Superior": "badge-superior",
        "Average": "badge-average",
        "Basic": "badge-basic",
        "No Coverage": "badge-none",
    }
    return mapping.get(rating, "badge-none")


def render_html_report(analysis, risk_quantification_html: str = "") -> str:
    """Render the analysis results into an HTML report.

    Args:
        analysis: PolicyAnalysis object with all scores and narrative.
        risk_quantification_html: Pre-computed risk quantification HTML content.

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
        risk_quantification_html=Markup(risk_quantification_html) if risk_quantification_html else "",
        generation_date=datetime.now().strftime("%B %d, %Y"),
    )

    return html


def generate_pdf_report(analysis, output_path: Path, risk_quantification_html: str = "") -> Path:
    """Generate a branded PDF report from the analysis results.

    Args:
        analysis: PolicyAnalysis object.
        output_path: Path to write the PDF file.
        risk_quantification_html: Pre-computed risk quantification HTML content.

    Returns:
        Path to the generated PDF.
    """
    from weasyprint import HTML

    logger.info("Rendering HTML report")
    html_content = render_html_report(analysis, risk_quantification_html=risk_quantification_html)

    logger.info("Converting HTML to PDF: %s", output_path)
    settings = get_settings()
    base_url = str(settings.templates_dir)

    HTML(string=html_content, base_url=base_url).write_pdf(str(output_path))

    logger.info("PDF generated: %s (%.1f KB)", output_path, output_path.stat().st_size / 1024)
    return output_path

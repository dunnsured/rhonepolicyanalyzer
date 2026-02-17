"""PDF extraction module using PyMuPDF4LLM and pdfplumber."""

import logging
from pathlib import Path

import pymupdf4llm
import pdfplumber

logger = logging.getLogger(__name__)


def extract_pdf_to_markdown(pdf_path: Path) -> str:
    """Extract PDF content to LLM-ready Markdown using PyMuPDF4LLM.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Markdown string with document structure preserved.
    """
    logger.info("Extracting PDF to markdown: %s", pdf_path)
    md_text = pymupdf4llm.to_markdown(str(pdf_path))
    logger.info("Extracted %d characters of markdown", len(md_text))
    return md_text


def extract_tables(pdf_path: Path) -> list[dict]:
    """Extract tables from PDF using pdfplumber for precise numeric data.

    Targets coverage schedules, premium breakdowns, and limit tables.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        List of table dicts with page number and rows.
    """
    logger.info("Extracting tables from: %s", pdf_path)
    tables = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages):
            page_tables = page.extract_tables()
            for table in page_tables:
                if not table or len(table) < 2:
                    continue
                # Use first row as headers if it looks like a header
                headers = table[0] if table[0] else None
                rows = table[1:] if headers else table
                tables.append({
                    "page": i + 1,
                    "headers": headers,
                    "rows": rows,
                })

    logger.info("Extracted %d tables", len(tables))
    return tables


def format_tables_for_context(tables: list[dict]) -> str:
    """Format extracted tables as readable text for AI context.

    Args:
        tables: List of table dicts from extract_tables.

    Returns:
        Formatted string with all tables.
    """
    if not tables:
        return ""

    parts = ["\n## Extracted Tables\n"]
    for i, table in enumerate(tables, 1):
        parts.append(f"\n### Table {i} (Page {table['page']})\n")
        if table["headers"]:
            header_row = " | ".join(str(h or "") for h in table["headers"])
            parts.append(f"| {header_row} |")
            parts.append("| " + " | ".join("---" for _ in table["headers"]) + " |")
        for row in table["rows"]:
            row_text = " | ".join(str(cell or "") for cell in row)
            parts.append(f"| {row_text} |")

    return "\n".join(parts)


def extract_policy(pdf_path: Path) -> tuple[str, list[dict]]:
    """Full extraction pipeline: markdown text + structured tables.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Tuple of (markdown_text, tables).
    """
    md_text = extract_pdf_to_markdown(pdf_path)
    tables = extract_tables(pdf_path)
    return md_text, tables

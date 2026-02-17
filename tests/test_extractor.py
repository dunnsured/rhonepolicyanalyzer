"""Tests for PDF extraction module."""

from pathlib import Path
from unittest.mock import patch, MagicMock

from app.etl.extractor import format_tables_for_context


def test_format_tables_for_context_empty():
    result = format_tables_for_context([])
    assert result == ""


def test_format_tables_for_context_with_data():
    tables = [
        {
            "page": 1,
            "headers": ["Coverage", "Limit", "Deductible"],
            "rows": [
                ["Network Security", "$5,000,000", "$25,000"],
                ["Privacy Liability", "$5,000,000", "$25,000"],
            ],
        }
    ]
    result = format_tables_for_context(tables)

    assert "Table 1" in result
    assert "Page 1" in result
    assert "Coverage" in result
    assert "Network Security" in result
    assert "$5,000,000" in result


def test_format_tables_without_headers():
    tables = [
        {
            "page": 2,
            "headers": None,
            "rows": [
                ["Row 1 Col 1", "Row 1 Col 2"],
                ["Row 2 Col 1", "Row 2 Col 2"],
            ],
        }
    ]
    result = format_tables_for_context(tables)

    assert "Table 1" in result
    assert "Row 1 Col 1" in result


def test_format_tables_multiple():
    tables = [
        {"page": 1, "headers": ["A", "B"], "rows": [["1", "2"]]},
        {"page": 3, "headers": ["C", "D"], "rows": [["3", "4"]]},
    ]
    result = format_tables_for_context(tables)

    assert "Table 1" in result
    assert "Table 2" in result
    assert "Page 1" in result
    assert "Page 3" in result

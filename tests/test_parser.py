"""Tests for metadata parsing."""

from app.etl.parser import parse_metadata


def test_parse_policy_number(sample_policy_text):
    meta = parse_metadata(sample_policy_text)
    assert meta.policy_number == "CYB-2026-001234"


def test_parse_carrier(sample_policy_text):
    meta = parse_metadata(sample_policy_text)
    assert "Great American" in meta.carrier_name


def test_parse_named_insured(sample_policy_text):
    meta = parse_metadata(sample_policy_text)
    assert meta.named_insured == "Acme Corporation"


def test_parse_effective_date(sample_policy_text):
    meta = parse_metadata(sample_policy_text)
    assert meta.effective_date == "03/01/2026"


def test_parse_expiration_date(sample_policy_text):
    meta = parse_metadata(sample_policy_text)
    assert meta.expiration_date == "03/01/2027"


def test_parse_aggregate_limit(sample_policy_text):
    meta = parse_metadata(sample_policy_text)
    assert "5,000,000" in meta.aggregate_limit


def test_parse_deductible(sample_policy_text):
    meta = parse_metadata(sample_policy_text)
    assert "25,000" in meta.deductible


def test_parse_premium(sample_policy_text):
    meta = parse_metadata(sample_policy_text)
    assert "45,000" in meta.premium


def test_parse_retroactive_date(sample_policy_text):
    meta = parse_metadata(sample_policy_text)
    assert "full prior acts" in meta.retroactive_date.lower() or "Full Prior Acts" in meta.retroactive_date


def test_parse_empty_text():
    meta = parse_metadata("")
    assert meta.policy_number == ""
    assert meta.carrier_name == ""


def test_parse_partial_text():
    text = "Policy Number: XYZ-999\nSome other text without dates."
    meta = parse_metadata(text)
    assert meta.policy_number == "XYZ-999"
    assert meta.effective_date == ""

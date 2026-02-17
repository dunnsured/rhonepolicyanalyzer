"""Regex-based metadata parsing for policy documents."""

import re
import logging

from app.models.scoring import PolicyMetadata

logger = logging.getLogger(__name__)

# Patterns for common policy metadata fields
PATTERNS = {
    "policy_number": [
        r"(?i)policy\s*(?:number|no\.?|#)\s*[:;]?\s*([A-Z0-9][\w\-\/]{4,30})",
    ],
    "carrier_name": [
        r"(?i)(?:insurer|carrier|underwriter|issued\s+by)\s*[:;]?\s*(.+?)(?:\n|$)",
    ],
    "named_insured": [
        r"(?i)(?:named\s+insured|insured|policyholder)\s*[:;]?\s*(.+?)(?:\n|$)",
    ],
    "effective_date": [
        r"(?i)(?:effective|inception)\s*(?:date)?\s*[:;]?\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})",
        r"(?i)(?:effective|inception)\s*(?:date)?\s*[:;]?\s*(\w+\s+\d{1,2},?\s+\d{4})",
    ],
    "expiration_date": [
        r"(?i)(?:expiration|expiry)\s*(?:date)?\s*[:;]?\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})",
        r"(?i)(?:expiration|expiry)\s*(?:date)?\s*[:;]?\s*(\w+\s+\d{1,2},?\s+\d{4})",
    ],
    "aggregate_limit": [
        r"(?i)(?:aggregate|policy)\s*(?:limit|maximum)\s*[:;]?\s*\$?([\d,]+(?:\.\d{2})?)",
    ],
    "per_occurrence_limit": [
        r"(?i)(?:per\s+(?:occurrence|claim|event))\s*(?:limit)?\s*[:;]?\s*\$?([\d,]+(?:\.\d{2})?)",
        r"(?i)(?:each\s+(?:claim|occurrence))\s*[:;]?\s*\$?([\d,]+(?:\.\d{2})?)",
    ],
    "deductible": [
        r"(?i)(?:deductible|retention|SIR)\s*[:;]?\s*\$?([\d,]+(?:\.\d{2})?)",
    ],
    "premium": [
        r"(?i)(?:total\s+)?(?:annual\s+)?premium\s*[:;]?\s*\$?([\d,]+(?:\.\d{2})?)",
    ],
    "retroactive_date": [
        r"(?i)retroactive\s*(?:date)?\s*[:;]?\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})",
        r"(?i)retroactive\s*(?:date)?\s*[:;]?\s*(\w+\s+\d{1,2},?\s+\d{4})",
        r"(?i)retroactive\s*(?:date)?\s*[:;]?\s*(full\s+prior\s+acts|unlimited|none)",
    ],
    "policy_form": [
        r"(?i)(?:policy\s+form|form\s+(?:number|no))\s*[:;]?\s*([A-Z0-9][\w\-\s]{2,30})",
    ],
}


def parse_metadata(text: str) -> PolicyMetadata:
    """Extract policy metadata from document text using regex patterns.

    Args:
        text: Full extracted text from the policy PDF.

    Returns:
        PolicyMetadata with all fields that could be extracted.
    """
    metadata = {}

    for field, patterns in PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                value = match.group(1).strip()
                metadata[field] = value
                logger.debug("Parsed %s: %s", field, value)
                break

    result = PolicyMetadata(**metadata)
    filled = sum(1 for v in metadata.values() if v)
    logger.info("Parsed %d/%d metadata fields", filled, len(PATTERNS))
    return result

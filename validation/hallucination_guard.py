"""
Hallucination Guard — from master build prompt.
Detects potentially hallucinated values in financial extractions.
Flags anything that is statistically impossible or logically inconsistent.
"""

from typing import List, Tuple
from config import CONFIDENCE_THRESHOLD
from loguru import logger


class HallucinationGuard:
    """
    Detects potentially hallucinated values in financial extractions.
    Flags anything that is statistically impossible or logically inconsistent.
    """

    # Known impossible value ranges for financial fields
    IMPOSSIBLE_RANGES = {
        "tax_rate": (0, 1.0),             # Tax rate must be 0-100%
        "confidence": (0, 1.0),
        "total_amount": (0, 100_000_000), # Invoice total max $100M
        "claimed_amount": (0, 10_000_000),
        "policy_limit": (0, 100_000_000),
        "page_count": (1, 1000),
    }

    def scan_extractions(self, fields: dict, doc_type: str) -> List[Tuple[str, str]]:
        """
        Returns list of (field_name, reason) for flagged fields.
        """
        flags = []

        for field_name, field_data in fields.items():
            if not isinstance(field_data, dict):
                continue

            value = field_data.get("value")
            confidence = field_data.get("confidence", 1.0)

            # Flag 1: Low confidence
            if confidence < CONFIDENCE_THRESHOLD:
                flags.append((field_name, f"Low confidence: {confidence:.2f} < threshold {CONFIDENCE_THRESHOLD}"))

            # Flag 2: Impossible range
            if field_name in self.IMPOSSIBLE_RANGES and value is not None:
                min_val, max_val = self.IMPOSSIBLE_RANGES[field_name]
                try:
                    numeric = float(value)
                    if not (min_val <= numeric <= max_val):
                        flags.append((field_name, f"Value {numeric} outside valid range [{min_val}, {max_val}]"))
                except (ValueError, TypeError):
                    pass

            # Flag 3: Empty or None value with high confidence (contradiction)
            if (value is None or value == "") and confidence > 0.9:
                flags.append((field_name, f"Null value with high confidence {confidence:.2f} — contradiction"))

            # Flag 4: Currency amount looks like a date or vice versa
            if "amount" in field_name or "total" in field_name or "price" in field_name:
                if isinstance(value, str) and ("-" in value or "/" in value):
                    flags.append((field_name, f"Currency field '{field_name}' contains date-like value: '{value}'"))

            # Flag 5: Negative amounts where none expected
            negative_impossible_fields = ["total_amount", "subtotal", "tax_amount", "policy_limit", "claimed_amount"]
            if field_name in negative_impossible_fields and value is not None:
                try:
                    if float(value) < 0:
                        flags.append((field_name, f"Negative value {value} in field that must be positive"))
                except (ValueError, TypeError):
                    pass

        logger.info(f"Hallucination scan complete: {len(flags)} flags found")
        return flags

    def calculate_hallucination_score(self, flags: list, total_fields: int) -> float:
        """
        Returns a clean score 0-100 (100 = no hallucinations).
        """
        if total_fields == 0:
            return 100.0
        clean_fields = total_fields - len(flags)
        return round((clean_fields / total_fields) * 100, 2)

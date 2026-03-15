"""
Field Mapper — Normalizes HyperAPI responses into standardized ExtractionResult objects.
Handles 3 possible response shapes:
  Shape A: {fields: {field_name: {value, confidence}}}
  Shape B: {data: [{key, value, confidence}]}
  Shape C: {extracted_fields: {field_name: value}}  (flat, no confidence)
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from loguru import logger


@dataclass
class ExtractedField:
    """A single extracted field with its value and confidence."""
    field_name: str
    value: Any
    confidence: float = 0.0
    source: str = "hyper_api"  # 'hyper_api' or 'claude'


@dataclass
class ExtractionResult:
    """Standardized extraction result regardless of API response shape."""
    doc_type: str
    fields: dict[str, ExtractedField] = field(default_factory=dict)
    raw_response: Optional[dict] = None
    response_shape: Optional[str] = None

    @property
    def field_values(self) -> dict[str, Any]:
        """Get a flat dict of field_name → value."""
        return {name: f.value for name, f in self.fields.items()}

    @property
    def field_confidences(self) -> dict[str, float]:
        """Get a flat dict of field_name → confidence."""
        return {name: f.confidence for name, f in self.fields.items()}

    @property
    def avg_confidence(self) -> float:
        """Average confidence across all fields."""
        if not self.fields:
            return 0.0
        return sum(f.confidence for f in self.fields.values()) / len(self.fields)

    @property
    def completeness(self) -> float:
        """Fraction of fields that have non-null values."""
        if not self.fields:
            return 0.0
        non_null = sum(1 for f in self.fields.values() if f.value is not None)
        return non_null / len(self.fields)

    def get_missing_fields(self) -> list[str]:
        """Return field names that are null/empty."""
        return [
            name for name, f in self.fields.items()
            if f.value is None or f.value == "" or f.value == []
        ]


class FieldMapper:
    """Maps raw API responses to standardized ExtractionResult objects."""

    def map_response(self, raw_response: dict, doc_type: str) -> ExtractionResult:
        """
        Detect the response shape and map to ExtractionResult.
        Tries Shape A, then B, then C.
        """
        shape = self._detect_shape(raw_response)
        logger.info(f"Detected response shape: {shape}")

        if shape == "A":
            result = self._map_shape_a(raw_response, doc_type)
        elif shape == "B":
            result = self._map_shape_b(raw_response, doc_type)
        elif shape == "C":
            result = self._map_shape_c(raw_response, doc_type)
        else:
            logger.warning(f"Unknown response shape — attempting best-effort mapping")
            result = self._map_best_effort(raw_response, doc_type)

        result.raw_response = raw_response
        result.response_shape = shape

        logger.info(
            f"Mapped {len(result.fields)} fields from shape {shape}, "
            f"avg confidence: {result.avg_confidence:.2f}, "
            f"completeness: {result.completeness:.1%}"
        )
        return result

    def _detect_shape(self, response: dict) -> str:
        """Detect which response shape the API returned."""
        if "fields" in response and isinstance(response["fields"], dict):
            # Check if it's Shape A: values are dicts with 'value' key
            sample = next(iter(response["fields"].values()), None)
            if isinstance(sample, dict) and "value" in sample:
                return "A"

        if "data" in response and isinstance(response["data"], list):
            # Shape B: list of {key, value, confidence}
            if response["data"] and isinstance(response["data"][0], dict):
                if "key" in response["data"][0]:
                    return "B"

        if "extracted_fields" in response and isinstance(response["extracted_fields"], dict):
            return "C"

        return "unknown"

    def _map_shape_a(self, response: dict, doc_type: str) -> ExtractionResult:
        """
        Map Shape A: {fields: {field_name: {value, confidence}}}
        """
        result = ExtractionResult(doc_type=doc_type)

        for field_name, field_data in response.get("fields", {}).items():
            if isinstance(field_data, dict):
                result.fields[field_name] = ExtractedField(
                    field_name=field_name,
                    value=field_data.get("value"),
                    confidence=float(field_data.get("confidence", 0.0)),
                    source="hyper_api",
                )
            else:
                # If value is not a dict, treat as flat value
                result.fields[field_name] = ExtractedField(
                    field_name=field_name,
                    value=field_data,
                    confidence=0.5,
                    source="hyper_api",
                )

        return result

    def _map_shape_b(self, response: dict, doc_type: str) -> ExtractionResult:
        """
        Map Shape B: {data: [{key, value, confidence}]}
        """
        result = ExtractionResult(doc_type=doc_type)

        for item in response.get("data", []):
            if isinstance(item, dict) and "key" in item:
                field_name = item["key"]
                result.fields[field_name] = ExtractedField(
                    field_name=field_name,
                    value=item.get("value"),
                    confidence=float(item.get("confidence", 0.0)),
                    source="hyper_api",
                )

        return result

    def _map_shape_c(self, response: dict, doc_type: str) -> ExtractionResult:
        """
        Map Shape C: {extracted_fields: {field_name: value}} (flat, no confidence)
        Default confidence = 0.5 since shape C doesn't provide it.
        """
        result = ExtractionResult(doc_type=doc_type)

        for field_name, value in response.get("extracted_fields", {}).items():
            result.fields[field_name] = ExtractedField(
                field_name=field_name,
                value=value,
                confidence=0.5,  # Default for no-confidence responses
                source="hyper_api",
            )

        return result

    def _map_best_effort(self, response: dict, doc_type: str) -> ExtractionResult:
        """Best-effort mapping for unknown response shapes."""
        result = ExtractionResult(doc_type=doc_type)

        # Try to extract any key-value pairs from the response
        for key, value in response.items():
            if isinstance(value, (str, int, float, bool)):
                result.fields[key] = ExtractedField(
                    field_name=key,
                    value=value,
                    confidence=0.3,
                    source="hyper_api",
                )
            elif isinstance(value, dict) and "value" in value:
                result.fields[key] = ExtractedField(
                    field_name=key,
                    value=value["value"],
                    confidence=float(value.get("confidence", 0.3)),
                    source="hyper_api",
                )

        return result

    def merge_claude_results(
        self, extraction: ExtractionResult, claude_fields: list[dict]
    ) -> ExtractionResult:
        """
        Merge Claude gap-fill results into an existing ExtractionResult.
        Only fills null/empty fields — never overwrites.
        """
        filled = 0
        for item in claude_fields:
            field_name = item.get("field_name", "")
            value = item.get("value")
            confidence = float(item.get("confidence", 0.5))

            existing = extraction.fields.get(field_name)
            if existing is None or existing.value is None or existing.value == "":
                extraction.fields[field_name] = ExtractedField(
                    field_name=field_name,
                    value=value,
                    confidence=confidence,
                    source="claude",
                )
                filled += 1

        logger.info(f"Merged {filled} Claude fields into extraction result")
        return extraction

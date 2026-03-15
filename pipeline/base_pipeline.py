"""
Base Pipeline — Abstract base class for document processing.
extract → validate → store → score flow with error resilience.
Fallback: HyperAPI → Local Regex Extractor (zero external dependencies).
Never calls any external AI service. Only HyperAPI is external.
"""

import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from loguru import logger

from extraction.hyper_client import HyperAPIClient
from extraction.local_extractor import LocalExtractor
from validation.math_validator import MathValidator
from validation.hallucination_guard import HallucinationGuard
from scoring.accuracy_scorer import AccuracyScorer
from database.db import SessionLocal
from database import crud


class BasePipeline(ABC):
    """
    Abstract base class for document processing pipelines.
    Flow: extract() → validate() → store() → score()

    Fallback chain:
    1. HyperAPI (primary extraction)
    2. Local Regex Extractor (gap-fill or full fallback)
    No external AI, no internet dependency for fallback.
    """

    def __init__(self):
        self.hyper_client = HyperAPIClient()
        self.local_extractor = LocalExtractor()
        self.math_validator = MathValidator()
        self.hallucination_guard = HallucinationGuard()
        self.scorer = AccuracyScorer()

        # Track what was used
        self.hyperapi_used = False
        self.local_fallback_used = False

    @property
    @abstractmethod
    def doc_type(self) -> str:
        """Return the document type this pipeline handles."""
        ...

    async def run(self, file_path: str, text: str, document_id: int) -> dict:
        """Execute the full pipeline with error resilience."""
        start_time = time.time()
        db = SessionLocal()
        pipeline_run = None

        try:
            # Create pipeline run record
            pipeline_run = crud.create_pipeline_run(db, document_id, self.doc_type)
            crud.update_document_status(db, document_id, "processing")

            # ── Stage 1: Extract ──────────────────────────────────────
            raw_response, fields, line_items = await self._safe_extract(file_path, text)

            # ── Stage 2: Validate ─────────────────────────────────────
            validation_checks, hallucination_flags = self._safe_validate(fields, line_items)

            # ── Stage 3: Store ────────────────────────────────────────
            self._safe_store(db, document_id, fields, line_items, validation_checks, hallucination_flags)

            # ── Stage 4: Score ────────────────────────────────────────
            accuracy_score, validation_pass_rate, hallucination_score = self._safe_score(
                validation_checks, hallucination_flags, fields
            )

            # Determine final status
            status = "done"
            if not fields:
                status = "failed"
            elif not self.hyperapi_used and not self.local_fallback_used:
                status = "failed"

            # Update pipeline run
            elapsed = time.time() - start_time
            crud.update_pipeline_run(
                db, pipeline_run.id,
                success=(status == "done"),
                hyperapi_used=self.hyperapi_used,
                claude_fallback_used=self.local_fallback_used,
                fields_extracted=len(fields),
                fields_validated=len(validation_checks),
                validation_pass_rate=validation_pass_rate,
                accuracy_score=accuracy_score,
            )
            crud.update_document_status(db, document_id, status)

            logger.info(
                f"Pipeline complete for doc #{document_id}: "
                f"status={status}, accuracy={accuracy_score:.1f}, "
                f"elapsed={elapsed:.2f}s"
            )

            return {
                "document_id": document_id,
                "doc_type": self.doc_type,
                "status": status,
                "fields": fields,
                "line_items": line_items,
                "validation_checks": [
                    {
                        "check_name": c.check_name,
                        "check_category": c.check_category,
                        "expected_value": c.expected_value,
                        "actual_value": c.actual_value,
                        "passed": c.passed,
                        "diff_amount": c.diff_amount,
                        "diff_percent": c.diff_percent,
                        "notes": c.notes,
                    }
                    for c in validation_checks
                ],
                "hallucination_flags": [
                    {"field": f[0], "reason": f[1]}
                    for f in hallucination_flags
                ],
                "scores": {
                    "accuracy_score": accuracy_score,
                    "validation_pass_rate": validation_pass_rate,
                    "hallucination_score": hallucination_score,
                    "fields_extracted": len(fields),
                    "math_checks_passed": sum(1 for c in validation_checks if c.passed),
                    "math_checks_total": len(validation_checks),
                },
                "pipeline_run_id": pipeline_run.id if pipeline_run else None,
                "duration_seconds": round(time.time() - start_time, 2),
                "hyperapi_used": self.hyperapi_used,
                "local_fallback_used": self.local_fallback_used,
            }

        except Exception as e:
            logger.error(f"Pipeline failed for doc #{document_id}: {e}")
            if pipeline_run:
                crud.update_pipeline_run(
                    db, pipeline_run.id,
                    success=False,
                    error_message=str(e),
                )
            crud.update_document_status(db, document_id, "failed")
            raise
        finally:
            db.close()

    async def _safe_extract(self, file_path: str, text: str) -> tuple:
        """
        Extract with error resilience:
        1. Try HyperAPI first (primary extraction)
        2. If HyperAPI fails or has gaps → Local Regex Extractor fills gaps
        No external AI, no internet dependency for fallback.
        Returns (raw_response, fields_dict, line_items_list)
        """
        raw_response = {}
        fields = {}
        line_items = []

        # ── Try HyperAPI ──
        try:
            logger.info(f"[{self.doc_type}] Stage 1a: HyperAPI extraction")
            raw_response = await self.hyper_client.extract_document(file_path, self.doc_type)
            fields = raw_response.get("fields", {})
            line_items = raw_response.get("line_items", [])
            self.hyperapi_used = True
            logger.info(f"HyperAPI extracted {len(fields)} fields, {len(line_items)} line items")
        except Exception as e:
            logger.error(f"HyperAPI extraction failed: {e} — switching to local regex fallback")
            self.hyperapi_used = False

        # ── Local Regex Fallback ──
        try:
            # Check for gaps in HyperAPI results
            has_gaps = any(
                isinstance(v, dict) and v.get("value") is None
                for v in fields.values()
            )

            if has_gaps and self.hyperapi_used:
                # Gap-fill mode: only fill what HyperAPI missed
                logger.info(f"[{self.doc_type}] Stage 1b: Local regex gap-fill")
                fields = self.local_extractor.fill_gaps(fields, file_path, self.doc_type)
                self.local_fallback_used = True
            elif not self.hyperapi_used:
                # Full local extraction (HyperAPI failed completely)
                logger.info(f"[{self.doc_type}] Stage 1b: Full local regex extraction (HyperAPI unavailable)")
                fields = self.local_extractor.extract(file_path, self.doc_type)
                self.local_fallback_used = True
        except Exception as e:
            logger.error(f"Local extractor failed: {e} — storing partial results")

        return raw_response, fields, line_items

    def _safe_validate(self, fields: dict, line_items: list) -> tuple:
        """Validate with error resilience. Returns (checks, flags)."""
        validation_checks = []
        hallucination_flags = []

        # Math validation
        try:
            logger.info(f"[{self.doc_type}] Stage 2a: Math validation")
            if self.doc_type == "invoice":
                validation_checks = self.math_validator.validate_invoice(fields, line_items)
            elif self.doc_type == "tax_1040":
                validation_checks = self.math_validator.validate_tax_1040(fields)
            elif self.doc_type == "insurance":
                validation_checks = self.math_validator.validate_insurance(fields)
        except Exception as e:
            logger.error(f"Math validation failed: {e}")

        # Hallucination check
        try:
            logger.info(f"[{self.doc_type}] Stage 2b: Hallucination guard")
            hallucination_flags = self.hallucination_guard.scan_extractions(fields, self.doc_type)
        except Exception as e:
            logger.error(f"Hallucination check failed: {e}")

        return validation_checks, hallucination_flags

    def _safe_store(
        self, db, document_id: int,
        fields: dict, line_items: list,
        validation_checks: list, hallucination_flags: list,
    ):
        """Store all results to database."""
        try:
            logger.info(f"[{self.doc_type}] Stage 3: Storing results")

            # Store extractions (per-field)
            source = "hyperapi" if self.hyperapi_used else "local_regex"
            crud.bulk_create_extractions(db, document_id, fields, extraction_source=source)

            # Store line items
            if line_items:
                crud.bulk_create_line_items(db, document_id, line_items)

            # Store validation results
            if validation_checks:
                crud.bulk_create_validation_results(db, document_id, validation_checks)

            # Flag hallucinated fields
            if hallucination_flags:
                flagged_names = [f[0] for f in hallucination_flags]
                crud.flag_extractions_by_name(db, document_id, flagged_names)

        except Exception as e:
            logger.error(f"Failed to store results: {e}")

    def _safe_score(self, validation_checks, hallucination_flags, fields) -> tuple:
        """Calculate scores. Returns (accuracy_score, pass_rate, hallucination_score)."""
        try:
            logger.info(f"[{self.doc_type}] Stage 4: Scoring")

            # Validation pass rate
            if validation_checks:
                passed = sum(1 for c in validation_checks if c.passed)
                validation_pass_rate = round((passed / len(validation_checks)) * 100, 2)
            else:
                validation_pass_rate = 100.0

            # Hallucination score
            total_fields = len(fields)
            hallucination_score = self.hallucination_guard.calculate_hallucination_score(
                hallucination_flags, total_fields
            )

            # Overall accuracy score (weighted)
            accuracy_score = self.scorer.calculate_score(
                validation_pass_rate=validation_pass_rate,
                hallucination_score=hallucination_score,
                completeness=self._calc_completeness(fields),
                avg_confidence=self._calc_avg_confidence(fields),
            )

            return accuracy_score, validation_pass_rate, hallucination_score

        except Exception as e:
            logger.error(f"Scoring failed: {e}")
            return 0.0, 0.0, 100.0

    def _calc_completeness(self, fields: dict) -> float:
        """Calculate field completeness 0-100."""
        if not fields:
            return 0.0
        non_null = sum(
            1 for v in fields.values()
            if (isinstance(v, dict) and v.get("value") is not None)
            or (not isinstance(v, dict) and v is not None)
        )
        return round((non_null / len(fields)) * 100, 2)

    def _calc_avg_confidence(self, fields: dict) -> float:
        """Calculate average confidence 0-1."""
        confidences = []
        for v in fields.values():
            if isinstance(v, dict):
                confidences.append(v.get("confidence", 0.5))
        if not confidences:
            return 0.5
        return sum(confidences) / len(confidences)

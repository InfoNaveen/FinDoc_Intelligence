"""
Unit Tests — Math Validator, Hallucination Guard, Schema Validator
Updated to match master build prompt schema.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from validation.math_validator import MathValidator
from validation.hallucination_guard import HallucinationGuard
from validation.schema_validator import validate_against_schema


# ============================================================
# Math Validator Tests — Invoice
# ============================================================

class TestMathValidatorInvoice:

    def setup_method(self):
        self.validator = MathValidator()

    def test_valid_invoice(self):
        """All math checks should pass for the mock invoice data."""
        fields = {
            "subtotal": {"value": 12450.00, "confidence": 0.95},
            "tax_rate": {"value": 0.18, "confidence": 0.93},
            "tax_amount": {"value": 2241.00, "confidence": 0.94},
            "total_amount": {"value": 14691.00, "confidence": 0.96},
        }
        line_items = [
            {"line": 1, "description": "Software License", "qty": 5, "unit_price": 1200.00, "total": 6000.00},
            {"line": 2, "description": "Implementation", "qty": 40, "unit_price": 150.00, "total": 6000.00},
            {"line": 3, "description": "Training", "qty": 1, "unit_price": 450.00, "total": 450.00},
        ]
        results = self.validator.validate_invoice(fields, line_items)
        failed = [r for r in results if not r.passed]
        assert len(failed) == 0, f"Failed checks: {[r.check_name for r in failed]}"

    def test_wrong_subtotal(self):
        """Should fail when line items don't sum to subtotal."""
        fields = {
            "subtotal": {"value": 15000.00, "confidence": 0.95},
            "tax_rate": {"value": 0.10, "confidence": 0.93},
            "tax_amount": {"value": 1500.00, "confidence": 0.94},
            "total_amount": {"value": 16500.00, "confidence": 0.96},
        }
        line_items = [
            {"qty": 1, "unit_price": 5000.00, "total": 5000.00},
            {"qty": 2, "unit_price": 3000.00, "total": 6000.00},
        ]
        results = self.validator.validate_invoice(fields, line_items)
        subtotal_check = [r for r in results if r.check_name == "line_items_sum_to_subtotal"]
        assert len(subtotal_check) > 0
        assert not subtotal_check[0].passed

    def test_wrong_total(self):
        """Should fail when subtotal + tax != total."""
        fields = {
            "subtotal": {"value": 1000.00, "confidence": 0.95},
            "tax_rate": {"value": 0.10, "confidence": 0.93},
            "tax_amount": {"value": 100.00, "confidence": 0.94},
            "total_amount": {"value": 1200.00, "confidence": 0.96},  # Should be 1100
        }
        results = self.validator.validate_invoice(fields, [])
        total_check = [r for r in results if "total" in r.check_name]
        assert any(not r.passed for r in total_check)

    def test_each_line_item_math(self):
        """Should validate qty × unit_price = total for each line."""
        fields = {"subtotal": {"value": 100.00}}
        line_items = [
            {"qty": 3, "unit_price": 10.00, "total": 30.00},   # Correct
            {"qty": 2, "unit_price": 25.00, "total": 60.00},   # Wrong! Should be 50
        ]
        results = self.validator.validate_invoice(fields, line_items)
        line_checks = [r for r in results if r.check_name.startswith("line_item_")]
        assert len(line_checks) == 2
        assert line_checks[0].passed      # Item 1 correct
        assert not line_checks[1].passed   # Item 2 wrong

    def test_accuracy_score(self):
        """Test accuracy score calculation."""
        fields = {
            "subtotal": {"value": 100.00},
            "tax_rate": {"value": 0.10},
            "tax_amount": {"value": 10.00},
            "total_amount": {"value": 110.00},
        }
        results = self.validator.validate_invoice(fields, [])
        score = self.validator.calculate_accuracy_score(results)
        assert score == 100.0


# ============================================================
# Math Validator Tests — Tax 1040
# ============================================================

class TestMathValidatorTax:

    def setup_method(self):
        self.validator = MathValidator()

    def test_valid_tax_return(self):
        """All checks should pass for the mock tax data."""
        fields = {
            "total_income": {"value": 87500.00},
            "adjusted_gross_income": {"value": 84200.00},
            "standard_deduction": {"value": 13850.00},
            "taxable_income": {"value": 70350.00},
            "total_tax": {"value": 11879.00},
            "withholding": {"value": 12500.00},
            "refund_amount": {"value": 621.00},
        }
        results = self.validator.validate_tax_1040(fields)
        failed = [r for r in results if not r.passed]
        assert len(failed) == 0, f"Failed: {[(r.check_name, r.notes) for r in failed]}"

    def test_wrong_taxable_income(self):
        """Should fail when AGI - deduction != taxable."""
        fields = {
            "adjusted_gross_income": {"value": 100000.00},
            "standard_deduction": {"value": 13850.00},
            "taxable_income": {"value": 90000.00},  # Wrong, should be 86150
        }
        results = self.validator.validate_tax_1040(fields)
        assert any(not r.passed for r in results)

    def test_agi_exceeds_income(self):
        """Should fail when AGI > total income."""
        fields = {
            "total_income": {"value": 50000.00},
            "adjusted_gross_income": {"value": 60000.00},  # Impossible
        }
        results = self.validator.validate_tax_1040(fields)
        agi_check = [r for r in results if r.check_name == "agi_lte_total_income"]
        assert len(agi_check) > 0
        assert not agi_check[0].passed


# ============================================================
# Math Validator Tests — Insurance
# ============================================================

class TestMathValidatorInsurance:

    def setup_method(self):
        self.validator = MathValidator()

    def test_valid_claim(self):
        """All checks should pass for the mock insurance data."""
        fields = {
            "claimed_amount": {"value": 8500.00},
            "policy_limit": {"value": 50000.00},
            "deductible": {"value": 1000.00},
            "approved_amount": {"value": 7500.00},
        }
        results = self.validator.validate_insurance(fields)
        failed = [r for r in results if not r.passed]
        assert len(failed) == 0

    def test_claim_exceeds_policy(self):
        """Should fail when claimed > policy limit."""
        fields = {
            "claimed_amount": {"value": 60000.00},
            "policy_limit": {"value": 50000.00},
        }
        results = self.validator.validate_insurance(fields)
        limit_check = [r for r in results if r.check_name == "claim_within_policy_limit"]
        assert len(limit_check) > 0
        assert not limit_check[0].passed


# ============================================================
# Hallucination Guard Tests
# ============================================================

class TestHallucinationGuard:

    def setup_method(self):
        self.guard = HallucinationGuard()

    def test_clean_invoice(self):
        """No flags for clean data with high confidence."""
        fields = {
            "subtotal": {"value": 12450.00, "confidence": 0.95},
            "total_amount": {"value": 14691.00, "confidence": 0.96},
            "tax_rate": {"value": 0.18, "confidence": 0.93},
        }
        flags = self.guard.scan_extractions(fields, "invoice")
        assert len(flags) == 0

    def test_low_confidence_flag(self):
        """Should flag fields below confidence threshold."""
        fields = {
            "vendor_name": {"value": "Acme", "confidence": 0.50},
        }
        flags = self.guard.scan_extractions(fields, "invoice")
        assert len(flags) > 0
        assert any("confidence" in f[1].lower() for f in flags)

    def test_impossible_tax_rate(self):
        """Should flag tax rate > 100%."""
        fields = {
            "tax_rate": {"value": 1.5, "confidence": 0.95},
        }
        flags = self.guard.scan_extractions(fields, "invoice")
        assert len(flags) > 0
        assert any("range" in f[1].lower() for f in flags)

    def test_negative_total(self):
        """Should flag negative total_amount."""
        fields = {
            "total_amount": {"value": -500.00, "confidence": 0.90},
        }
        flags = self.guard.scan_extractions(fields, "invoice")
        assert any("negative" in f[1].lower() for f in flags)

    def test_null_with_high_confidence(self):
        """Should flag null value with high confidence (contradiction)."""
        fields = {
            "vendor_name": {"value": None, "confidence": 0.95},
        }
        flags = self.guard.scan_extractions(fields, "invoice")
        assert any("contradiction" in f[1].lower() for f in flags)

    def test_hallucination_score_perfect(self):
        """Score should be 100 with no flags."""
        score = self.guard.calculate_hallucination_score([], 10)
        assert score == 100.0

    def test_hallucination_score_with_flags(self):
        """Score should decrease with flags."""
        flags = [("field1", "reason1"), ("field2", "reason2")]
        score = self.guard.calculate_hallucination_score(flags, 10)
        assert score == 80.0


# ============================================================
# Schema Validator Tests
# ============================================================

class TestSchemaValidator:

    def test_valid_invoice_schema(self):
        fields = {
            "invoice_number": "INV-001",
            "subtotal": 1000.00,
            "tax_rate": 0.08,
            "total_amount": 1080.00,
        }
        is_valid, errors, model = validate_against_schema(fields, "invoice")
        assert is_valid
        assert len(errors) == 0

    def test_invalid_tax_rate(self):
        """Tax rate > 1.0 should fail."""
        fields = {"tax_rate": 15.0}
        is_valid, errors, model = validate_against_schema(fields, "invoice")
        assert not is_valid

    def test_valid_tax_schema(self):
        fields = {
            "tax_year": "2024",
            "filing_status": "Single",
            "wages_salaries": 75000.00,
        }
        is_valid, errors, model = validate_against_schema(fields, "tax_1040")
        assert is_valid

    def test_unknown_doc_type(self):
        is_valid, errors, _ = validate_against_schema({}, "unknown_type")
        assert is_valid


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

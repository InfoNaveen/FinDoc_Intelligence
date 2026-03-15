"""
Math Validator — from master build prompt.
This is the biggest judging differentiator.
"""

from dataclasses import dataclass
from typing import List, Optional
from config import MATH_TOLERANCE, PERCENTAGE_TOLERANCE
from loguru import logger


@dataclass
class ValidationCheck:
    check_name: str
    check_category: str          # 'arithmetic', 'consistency', 'range', 'format'
    expected_value: Optional[float]
    actual_value: Optional[float]
    passed: bool
    diff_amount: float
    diff_percent: float
    notes: str


class MathValidator:

    def validate_invoice(self, fields: dict, line_items: list) -> List[ValidationCheck]:
        results = []

        subtotal = self._get_float(fields, "subtotal")
        tax_rate = self._get_float(fields, "tax_rate")
        tax_amount = self._get_float(fields, "tax_amount")
        total = self._get_float(fields, "total_amount")

        # CHECK 1: Line items sum to subtotal
        if line_items and subtotal:
            calc_subtotal = sum(
                item.get("qty", item.get("quantity", 1)) * item.get("unit_price", 0)
                for item in line_items
            )
            results.append(self._check(
                "line_items_sum_to_subtotal",
                "arithmetic",
                subtotal,
                round(calc_subtotal, 2),
                "Sum of (qty × unit_price) should equal subtotal"
            ))

        # CHECK 2: Each line item's total = qty × unit_price
        for i, item in enumerate(line_items):
            qty_key = "qty" if "qty" in item else "quantity"
            total_key = "total" if "total" in item else "amount"
            if all(k in item for k in [qty_key, "unit_price", total_key]):
                calc = round(item[qty_key] * item["unit_price"], 2)
                results.append(self._check(
                    f"line_item_{i+1}_arithmetic",
                    "arithmetic",
                    item[total_key],
                    calc,
                    f"Line {i+1}: {item.get('description', 'Item')[:30]}"
                ))

        # CHECK 3: Tax amount = subtotal × tax_rate
        if subtotal and tax_rate and tax_amount:
            calc_tax = round(subtotal * tax_rate, 2)
            results.append(self._check(
                "tax_calculation",
                "arithmetic",
                tax_amount,
                calc_tax,
                f"Tax: {subtotal} × {tax_rate} = {calc_tax}"
            ))

        # CHECK 4: Total = subtotal + tax
        if subtotal and tax_amount and total:
            calc_total = round(subtotal + tax_amount, 2)
            results.append(self._check(
                "subtotal_plus_tax_equals_total",
                "arithmetic",
                total,
                calc_total,
                "Subtotal + Tax should equal Total"
            ))

        # CHECK 5: Total is positive and reasonable
        if total:
            results.append(ValidationCheck(
                check_name="total_amount_range",
                check_category="range",
                expected_value=None,
                actual_value=total,
                passed=0 < total < 10_000_000,
                diff_amount=0,
                diff_percent=0,
                notes=f"Total ${total:,.2f} should be positive and < $10M"
            ))

        return results

    def validate_tax_1040(self, fields: dict) -> List[ValidationCheck]:
        results = []

        total_income = self._get_float(fields, "total_income")
        agi = self._get_float(fields, "adjusted_gross_income")
        std_deduction = self._get_float(fields, "standard_deduction")
        taxable_income = self._get_float(fields, "taxable_income")
        total_tax = self._get_float(fields, "total_tax")
        withholding = self._get_float(fields, "withholding")
        refund = self._get_float(fields, "refund_amount")
        amount_owed = self._get_float(fields, "amount_owed")

        # CHECK 1: Taxable income = AGI - Standard deduction
        if agi and std_deduction and taxable_income:
            calc_taxable = round(agi - std_deduction, 2)
            results.append(self._check(
                "taxable_income_calculation",
                "arithmetic",
                taxable_income,
                calc_taxable,
                "AGI - Standard Deduction = Taxable Income"
            ))

        # CHECK 2: Refund = Withholding - Tax (if refund)
        if withholding and total_tax and refund:
            calc_refund = round(withholding - total_tax, 2)
            results.append(self._check(
                "refund_calculation",
                "arithmetic",
                refund,
                calc_refund,
                "Withholding - Total Tax = Refund"
            ))

        # CHECK 3: Amount owed = Tax - Withholding (if owing)
        if withholding and total_tax and amount_owed:
            calc_owed = round(total_tax - withholding, 2)
            results.append(self._check(
                "amount_owed_calculation",
                "arithmetic",
                amount_owed,
                calc_owed,
                "Total Tax - Withholding = Amount Owed"
            ))

        # CHECK 4: AGI <= Total Income (adjustments only reduce)
        if total_income and agi:
            results.append(ValidationCheck(
                check_name="agi_lte_total_income",
                check_category="consistency",
                expected_value=total_income,
                actual_value=agi,
                passed=agi <= total_income,
                diff_amount=round(total_income - agi, 2),
                diff_percent=0,
                notes="AGI cannot exceed Total Income"
            ))

        # CHECK 5: Standard deduction within known IRS ranges
        if std_deduction:
            # 2023 IRS standard deductions: $13,850 single, $27,700 married
            reasonable = 12000 <= std_deduction <= 30000
            results.append(ValidationCheck(
                check_name="standard_deduction_irs_range",
                check_category="range",
                expected_value=None,
                actual_value=std_deduction,
                passed=reasonable,
                diff_amount=0,
                diff_percent=0,
                notes=f"${std_deduction:,.2f} should be $12K-$30K per IRS 2023 tables"
            ))

        return results

    def validate_insurance(self, fields: dict) -> List[ValidationCheck]:
        results = []

        claimed = self._get_float(fields, "claimed_amount")
        policy_limit = self._get_float(fields, "policy_limit")
        deductible = self._get_float(fields, "deductible")
        approved = self._get_float(fields, "approved_amount")

        # CHECK 1: Claimed amount <= Policy limit
        if claimed and policy_limit:
            results.append(ValidationCheck(
                check_name="claim_within_policy_limit",
                check_category="consistency",
                expected_value=policy_limit,
                actual_value=claimed,
                passed=claimed <= policy_limit,
                diff_amount=round(claimed - policy_limit, 2),
                diff_percent=0,
                notes=f"Claim ${claimed:,.2f} must not exceed policy limit ${policy_limit:,.2f}"
            ))

        # CHECK 2: Approved = Claimed - Deductible
        if claimed and deductible and approved:
            calc_approved = round(claimed - deductible, 2)
            results.append(self._check(
                "approved_amount_calculation",
                "arithmetic",
                approved,
                calc_approved,
                "Claimed - Deductible = Approved Amount"
            ))

        # CHECK 3: Approved <= Claimed
        if claimed and approved:
            results.append(ValidationCheck(
                check_name="approved_lte_claimed",
                check_category="consistency",
                expected_value=claimed,
                actual_value=approved,
                passed=approved <= claimed,
                diff_amount=round(approved - claimed, 2),
                diff_percent=0,
                notes="Approved cannot exceed claimed amount"
            ))

        # CHECK 4: Deductible > 0
        if deductible:
            results.append(ValidationCheck(
                check_name="deductible_positive",
                check_category="range",
                expected_value=None,
                actual_value=deductible,
                passed=deductible > 0,
                diff_amount=0,
                diff_percent=0,
                notes="Deductible should be positive"
            ))

        return results

    def _check(self, name: str, category: str, expected: float, actual: float, notes: str) -> ValidationCheck:
        diff = abs(expected - actual)
        diff_pct = (diff / expected * 100) if expected != 0 else 0
        passed = diff <= MATH_TOLERANCE or diff_pct <= (PERCENTAGE_TOLERANCE * 100)
        return ValidationCheck(
            check_name=name,
            check_category=category,
            expected_value=expected,
            actual_value=actual,
            passed=passed,
            diff_amount=round(diff, 4),
            diff_percent=round(diff_pct, 4),
            notes=notes
        )

    def _get_float(self, fields: dict, key: str) -> Optional[float]:
        val = fields.get(key, {})
        if isinstance(val, dict):
            val = val.get("value", None)
        try:
            return float(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    def calculate_accuracy_score(self, validation_results: list) -> float:
        """Returns 0-100 accuracy score based on validation checks"""
        if not validation_results:
            return 0.0
        passed = sum(1 for r in validation_results if r.passed)
        return round((passed / len(validation_results)) * 100, 2)

"""
Schema Validator — Pydantic models for each document type.
Validates structure and types of extracted data.
"""

from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ============================================================
# Invoice Schema
# ============================================================

class LineItem(BaseModel):
    """A single line item in an invoice."""
    description: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: Optional[float] = None


class InvoiceSchema(BaseModel):
    """Pydantic schema for invoice documents."""
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    vendor_name: Optional[str] = None
    vendor_address: Optional[str] = None
    bill_to_name: Optional[str] = None
    bill_to_address: Optional[str] = None
    subtotal: Optional[float] = None
    tax_rate: Optional[float] = None
    tax_amount: Optional[float] = None
    total_amount: Optional[float] = None
    currency: Optional[str] = Field(default="USD")
    payment_terms: Optional[str] = None
    line_items: Optional[list[LineItem]] = None

    @field_validator("tax_rate")
    @classmethod
    def tax_rate_must_be_fraction(cls, v):
        if v is not None and (v < 0 or v > 1.0):
            raise ValueError(f"tax_rate must be 0-1.0 (fraction), got {v}")
        return v


# ============================================================
# IRS 1040 Schema
# ============================================================

class Tax1040Schema(BaseModel):
    """Pydantic schema for IRS Form 1040."""
    tax_year: Optional[str] = None
    filing_status: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    ssn: Optional[str] = None
    spouse_first_name: Optional[str] = None
    spouse_last_name: Optional[str] = None
    address: Optional[str] = None
    wages_salaries: Optional[float] = None
    interest_income: Optional[float] = None
    dividend_income: Optional[float] = None
    capital_gains: Optional[float] = None
    total_income: Optional[float] = None
    adjustments: Optional[float] = None
    adjusted_gross_income: Optional[float] = None
    standard_deduction: Optional[float] = None
    taxable_income: Optional[float] = None
    tax_owed: Optional[float] = None
    federal_tax_withheld: Optional[float] = None
    refund_amount: Optional[float] = None

    @field_validator("filing_status")
    @classmethod
    def validate_filing_status(cls, v):
        valid_statuses = [
            "Single", "Married Filing Jointly", "Married Filing Separately",
            "Head of Household", "Qualifying Surviving Spouse",
        ]
        if v is not None and v not in valid_statuses:
            # Allow case-insensitive match
            for status in valid_statuses:
                if v.lower() == status.lower():
                    return status
        return v


# ============================================================
# Insurance Claim Schema
# ============================================================

class InsuranceClaimSchema(BaseModel):
    """Pydantic schema for insurance claim documents."""
    claim_number: Optional[str] = None
    policy_number: Optional[str] = None
    claim_date: Optional[str] = None
    loss_date: Optional[str] = None
    claimant_name: Optional[str] = None
    claimant_address: Optional[str] = None
    policy_type: Optional[str] = None
    coverage_amount: Optional[float] = None
    deductible: Optional[float] = None
    loss_description: Optional[str] = None
    damage_estimate: Optional[float] = None
    adjuster_name: Optional[str] = None
    adjuster_phone: Optional[str] = None
    claim_status: Optional[str] = None
    depreciation: Optional[float] = None
    actual_cash_value: Optional[float] = None
    replacement_cost: Optional[float] = None
    amount_paid: Optional[float] = None
    payment_date: Optional[str] = None


# ============================================================
# Schema Validation Helper
# ============================================================

SCHEMA_MAP = {
    "invoice": InvoiceSchema,
    "tax_1040": Tax1040Schema,
    "insurance_claim": InsuranceClaimSchema,
}


def validate_against_schema(fields: dict[str, Any], doc_type: str) -> tuple[bool, list[str], Any]:
    """
    Validate extracted fields against the Pydantic schema.
    Returns (is_valid, errors, validated_model).
    """
    schema_class = SCHEMA_MAP.get(doc_type)
    if not schema_class:
        return True, [f"No schema defined for doc_type '{doc_type}'"], None

    try:
        model = schema_class(**fields)
        return True, [], model
    except Exception as e:
        errors = []
        if hasattr(e, "errors"):
            for err in e.errors():
                field_path = " → ".join(str(loc) for loc in err["loc"])
                errors.append(f"{field_path}: {err['msg']}")
        else:
            errors.append(str(e))
        return False, errors, None

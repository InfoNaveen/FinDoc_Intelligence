"""
CRUD Operations — Matches the master build prompt schema exactly.
Operates on: Document, Extraction, LineItem, ValidationResult, PipelineRun
"""

from datetime import datetime
from typing import Optional, List

from sqlalchemy.orm import Session
from loguru import logger

from database.models import Document, Extraction, LineItem, ValidationResult, PipelineRun


# ============================================================
# Document CRUD
# ============================================================

def create_document(
    db: Session,
    filename: str,
    doc_type: str,
    raw_pdf_path: str,
    page_count: int = 0,
    file_size_kb: float = 0.0,
) -> Document:
    """Create a new document record."""
    doc = Document(
        filename=filename,
        doc_type=doc_type,
        raw_pdf_path=raw_pdf_path,
        page_count=page_count,
        file_size_kb=file_size_kb,
        status="pending",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    logger.info(f"Created document #{doc.id}: {filename} ({doc_type})")
    return doc


def get_document(db: Session, doc_id: int) -> Optional[Document]:
    return db.query(Document).filter(Document.id == doc_id).first()


def get_all_documents(db: Session, limit: int = 100) -> List[Document]:
    return db.query(Document).order_by(Document.upload_time.desc()).limit(limit).all()


def update_document_status(db: Session, doc_id: int, status: str) -> Optional[Document]:
    doc = get_document(db, doc_id)
    if doc:
        doc.status = status
        db.commit()
        db.refresh(doc)
    return doc


def get_document_with_results(db: Session, doc_id: int) -> Optional[Document]:
    """Get a document with all its related data eagerly loaded."""
    doc = get_document(db, doc_id)
    if doc:
        # Touch relationships to eagerly load them
        _ = doc.extractions
        _ = doc.line_items
        _ = doc.validation_results
        _ = doc.pipeline_runs
    return doc


# ============================================================
# Extraction CRUD (per-field storage)
# ============================================================

def create_extraction(
    db: Session,
    document_id: int,
    field_name: str,
    field_value: str,
    field_type: str = "string",
    confidence: float = 0.0,
    extraction_source: str = "hyperapi",
    is_flagged: bool = False,
) -> Extraction:
    """Create a single field extraction record."""
    ext = Extraction(
        document_id=document_id,
        field_name=field_name,
        field_value=str(field_value) if field_value is not None else None,
        field_type=field_type,
        confidence=confidence,
        extraction_source=extraction_source,
        is_flagged=is_flagged,
    )
    db.add(ext)
    db.commit()
    db.refresh(ext)
    return ext


def bulk_create_extractions(
    db: Session,
    document_id: int,
    fields: dict,
    extraction_source: str = "hyperapi",
) -> List[Extraction]:
    """Create extraction records for all fields in a dict."""
    records = []
    for field_name, field_data in fields.items():
        if isinstance(field_data, dict):
            value = field_data.get("value")
            confidence = field_data.get("confidence", 0.0)
        else:
            value = field_data
            confidence = 0.5

        field_type = _infer_field_type(field_name, value)

        ext = Extraction(
            document_id=document_id,
            field_name=field_name,
            field_value=str(value) if value is not None else None,
            field_type=field_type,
            confidence=float(confidence),
            extraction_source=extraction_source,
        )
        db.add(ext)
        records.append(ext)

    db.commit()
    for r in records:
        db.refresh(r)

    logger.info(f"Stored {len(records)} extractions for doc #{document_id} (source: {extraction_source})")
    return records


def get_extractions(db: Session, document_id: int) -> List[Extraction]:
    return (
        db.query(Extraction)
        .filter(Extraction.document_id == document_id)
        .order_by(Extraction.id)
        .all()
    )


def get_extractions_as_dict(db: Session, document_id: int) -> dict:
    """Get extractions as a {field_name: {value, confidence}} dict."""
    exts = get_extractions(db, document_id)
    return {
        e.field_name: {
            "value": e.field_value,
            "confidence": e.confidence,
            "source": e.extraction_source,
            "flagged": e.is_flagged,
        }
        for e in exts
    }


def flag_extraction(db: Session, extraction_id: int):
    """Mark an extraction as flagged by hallucination guard."""
    ext = db.query(Extraction).filter(Extraction.id == extraction_id).first()
    if ext:
        ext.is_flagged = True
        db.commit()


def flag_extractions_by_name(db: Session, document_id: int, field_names: list):
    """Flag multiple extractions by field name."""
    exts = (
        db.query(Extraction)
        .filter(Extraction.document_id == document_id, Extraction.field_name.in_(field_names))
        .all()
    )
    for ext in exts:
        ext.is_flagged = True
    db.commit()
    logger.info(f"Flagged {len(exts)} extractions for doc #{document_id}")


# ============================================================
# LineItem CRUD
# ============================================================

def create_line_item(
    db: Session,
    document_id: int,
    line_number: int,
    description: str,
    quantity: float,
    unit_price: float,
    line_total: float,
) -> LineItem:
    """Create a line item with automatic math validation."""
    calculated = round(quantity * unit_price, 2)
    discrepancy = round(abs(line_total - calculated), 2)
    is_valid = discrepancy <= 0.02  # $0.02 tolerance

    li = LineItem(
        document_id=document_id,
        line_number=line_number,
        description=description,
        quantity=quantity,
        unit_price=unit_price,
        line_total=line_total,
        calculated_total=calculated,
        is_mathematically_valid=is_valid,
        discrepancy=discrepancy,
    )
    db.add(li)
    db.commit()
    db.refresh(li)
    return li


def bulk_create_line_items(db: Session, document_id: int, items: list) -> List[LineItem]:
    """Create line items from a list of dicts."""
    records = []
    for i, item in enumerate(items):
        qty = float(item.get("qty", item.get("quantity", 1)))
        price = float(item.get("unit_price", 0))
        total = float(item.get("total", item.get("line_total", item.get("amount", 0))))
        calculated = round(qty * price, 2)
        discrepancy = round(abs(total - calculated), 2)

        li = LineItem(
            document_id=document_id,
            line_number=item.get("line", i + 1),
            description=item.get("description", ""),
            quantity=qty,
            unit_price=price,
            line_total=total,
            calculated_total=calculated,
            is_mathematically_valid=discrepancy <= 0.02,
            discrepancy=discrepancy,
        )
        db.add(li)
        records.append(li)

    db.commit()
    for r in records:
        db.refresh(r)
    logger.info(f"Stored {len(records)} line items for doc #{document_id}")
    return records


def get_line_items(db: Session, document_id: int) -> List[LineItem]:
    return (
        db.query(LineItem)
        .filter(LineItem.document_id == document_id)
        .order_by(LineItem.line_number)
        .all()
    )


# ============================================================
# ValidationResult CRUD
# ============================================================

def create_validation_result(
    db: Session,
    document_id: int,
    check_name: str,
    check_category: str,
    expected_value: Optional[float],
    actual_value: Optional[float],
    passed: bool,
    diff_amount: float = 0.0,
    diff_percent: float = 0.0,
    tolerance: float = 0.02,
    notes: str = "",
) -> ValidationResult:
    vr = ValidationResult(
        document_id=document_id,
        check_name=check_name,
        check_category=check_category,
        expected_value=expected_value,
        actual_value=actual_value,
        passed=passed,
        diff_amount=diff_amount,
        diff_percent=diff_percent,
        tolerance=tolerance,
        notes=notes,
    )
    db.add(vr)
    db.commit()
    db.refresh(vr)
    return vr


def bulk_create_validation_results(
    db: Session, document_id: int, checks: list
) -> List[ValidationResult]:
    """Store a list of ValidationCheck dataclass objects."""
    records = []
    for check in checks:
        vr = ValidationResult(
            document_id=document_id,
            check_name=check.check_name,
            check_category=check.check_category,
            expected_value=check.expected_value,
            actual_value=check.actual_value,
            passed=check.passed,
            diff_amount=check.diff_amount,
            diff_percent=check.diff_percent,
            notes=check.notes,
        )
        db.add(vr)
        records.append(vr)

    db.commit()
    for r in records:
        db.refresh(r)
    logger.info(f"Stored {len(records)} validation checks for doc #{document_id}")
    return records


def get_validation_results(db: Session, document_id: int) -> List[ValidationResult]:
    return (
        db.query(ValidationResult)
        .filter(ValidationResult.document_id == document_id)
        .order_by(ValidationResult.id)
        .all()
    )


# ============================================================
# PipelineRun CRUD
# ============================================================

def create_pipeline_run(
    db: Session,
    document_id: int,
    pipeline_type: str,
) -> PipelineRun:
    run = PipelineRun(
        document_id=document_id,
        pipeline_type=pipeline_type,
        started_at=datetime.utcnow(),
        success=False,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info(f"Started pipeline run #{run.id} for doc #{document_id}")
    return run


def update_pipeline_run(
    db: Session,
    run_id: int,
    success: Optional[bool] = None,
    error_message: Optional[str] = None,
    hyperapi_used: Optional[bool] = None,
    claude_fallback_used: Optional[bool] = None,
    fields_extracted: Optional[int] = None,
    fields_validated: Optional[int] = None,
    validation_pass_rate: Optional[float] = None,
    accuracy_score: Optional[float] = None,
) -> Optional[PipelineRun]:
    run = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
    if not run:
        return None

    if success is not None:
        run.success = success
    if error_message is not None:
        run.error_message = error_message
    if hyperapi_used is not None:
        run.hyperapi_used = hyperapi_used
    if claude_fallback_used is not None:
        run.claude_fallback_used = claude_fallback_used
    if fields_extracted is not None:
        run.fields_extracted = fields_extracted
    if fields_validated is not None:
        run.fields_validated = fields_validated
    if validation_pass_rate is not None:
        run.validation_pass_rate = validation_pass_rate
    if accuracy_score is not None:
        run.accuracy_score = accuracy_score

    if success is not None:
        run.completed_at = datetime.utcnow()
        if run.started_at:
            run.duration_seconds = (run.completed_at - run.started_at).total_seconds()

    db.commit()
    db.refresh(run)
    return run


def get_pipeline_runs(db: Session, document_id: int) -> List[PipelineRun]:
    return (
        db.query(PipelineRun)
        .filter(PipelineRun.document_id == document_id)
        .order_by(PipelineRun.started_at.desc())
        .all()
    )


def get_recent_pipeline_runs(db: Session, limit: int = 20) -> List[PipelineRun]:
    return (
        db.query(PipelineRun)
        .order_by(PipelineRun.started_at.desc())
        .limit(limit)
        .all()
    )


# ============================================================
# Helpers
# ============================================================

def _infer_field_type(field_name: str, value) -> str:
    """Infer the field type from the field name and value."""
    currency_fields = {"subtotal", "tax_amount", "total_amount", "claimed_amount",
                       "approved_amount", "policy_limit", "deductible", "refund_amount",
                       "total_tax", "withholding", "wages_salaries", "total_income",
                       "adjusted_gross_income", "taxable_income", "standard_deduction",
                       "amount_owed"}
    date_fields = {"invoice_date", "due_date", "claim_date", "incident_date", "payment_date"}
    number_fields = {"tax_rate", "page_count", "quantity", "unit_price"}

    if field_name in currency_fields:
        return "currency"
    elif field_name in date_fields:
        return "date"
    elif field_name in number_fields:
        return "number"
    else:
        return "string"

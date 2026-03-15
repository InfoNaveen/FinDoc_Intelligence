"""
FastAPI REST Endpoints — Upload, process, query documents.
Updated to match master prompt schema.
"""

import os
import asyncio
from typing import Optional

from fastapi import APIRouter, File, UploadFile, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from loguru import logger

from config import ALLOWED_EXTENSIONS, MAX_FILE_SIZE_MB
from database.db import get_db
from database import crud
from ingestion.document_loader import (
    validate_file, save_uploaded_file, preprocess_document, detect_document_type,
)
from pipeline.invoice_pipeline import InvoicePipeline
from pipeline.tax_pipeline import TaxPipeline
from pipeline.insurance_pipeline import InsurancePipeline


router = APIRouter(prefix="/api/v1", tags=["documents"])

# Pipeline registry
PIPELINES = {
    "invoice": InvoicePipeline,
    "tax_1040": TaxPipeline,
    "insurance": InsurancePipeline,
}


@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "FinDoc Intelligence Pipeline"}


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    doc_type: Optional[str] = Query(None, description="Document type: invoice, tax_1040, insurance"),
    db: Session = Depends(get_db),
):
    """Upload a PDF document for processing."""
    content = await file.read()
    is_valid, error = validate_file(file.filename, len(content))
    if not is_valid:
        raise HTTPException(status_code=400, detail=error)

    file_path = save_uploaded_file(file.filename, content)

    try:
        doc_info = preprocess_document(str(file_path))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Failed to process PDF: {e}")

    if not doc_type:
        doc_type = detect_document_type(doc_info["full_text"])
        if doc_type == "unknown":
            doc_type = "invoice"

    if doc_type not in PIPELINES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid doc_type '{doc_type}'. Must be one of: {list(PIPELINES.keys())}",
        )

    document = crud.create_document(
        db,
        filename=file.filename,
        doc_type=doc_type,
        raw_pdf_path=str(file_path),
        page_count=doc_info["page_count"],
        file_size_kb=doc_info["file_size_bytes"] / 1024,
    )

    pipeline = PIPELINES[doc_type]()
    try:
        result = await pipeline.run(str(file_path), doc_info["full_text"], document.id)
        return result
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")


@router.get("/documents")
async def list_documents(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    documents = crud.get_all_documents(db, limit=limit)
    return [
        {
            "id": doc.id,
            "filename": doc.filename,
            "doc_type": doc.doc_type,
            "status": doc.status,
            "page_count": doc.page_count,
            "upload_time": doc.upload_time.isoformat() if doc.upload_time else None,
        }
        for doc in documents
    ]


@router.get("/documents/{doc_id}")
async def get_document(doc_id: int, db: Session = Depends(get_db)):
    document = crud.get_document_with_results(db, doc_id)
    if not document:
        raise HTTPException(status_code=404, detail=f"Document #{doc_id} not found")

    extractions = crud.get_extractions_as_dict(db, doc_id)
    line_items = crud.get_line_items(db, doc_id)
    validations = crud.get_validation_results(db, doc_id)
    runs = crud.get_pipeline_runs(db, doc_id)
    latest_run = runs[0] if runs else None

    return {
        "document": {
            "id": document.id,
            "filename": document.filename,
            "doc_type": document.doc_type,
            "status": document.status,
            "page_count": document.page_count,
            "file_size_kb": document.file_size_kb,
            "upload_time": document.upload_time.isoformat() if document.upload_time else None,
        },
        "extractions": extractions,
        "line_items": [
            {
                "line_number": li.line_number,
                "description": li.description,
                "quantity": li.quantity,
                "unit_price": li.unit_price,
                "line_total": li.line_total,
                "calculated_total": li.calculated_total,
                "is_valid": li.is_mathematically_valid,
                "discrepancy": li.discrepancy,
            }
            for li in line_items
        ],
        "validations": [
            {
                "check_name": v.check_name,
                "check_category": v.check_category,
                "expected_value": v.expected_value,
                "actual_value": v.actual_value,
                "passed": v.passed,
                "diff_amount": v.diff_amount,
                "notes": v.notes,
            }
            for v in validations
        ],
        "scores": {
            "accuracy_score": latest_run.accuracy_score if latest_run else None,
            "validation_pass_rate": latest_run.validation_pass_rate if latest_run else None,
            "fields_extracted": latest_run.fields_extracted if latest_run else 0,
        },
    }


@router.get("/runs")
async def list_pipeline_runs(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    runs = crud.get_recent_pipeline_runs(db, limit=limit)
    return [
        {
            "id": run.id,
            "document_id": run.document_id,
            "pipeline_type": run.pipeline_type,
            "success": run.success,
            "accuracy_score": run.accuracy_score,
            "duration_seconds": run.duration_seconds,
            "started_at": run.started_at.isoformat() if run.started_at else None,
        }
        for run in runs
    ]

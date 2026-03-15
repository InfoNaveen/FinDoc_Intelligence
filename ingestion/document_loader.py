"""
Document Loader — PDF upload, preprocessing, page count extraction
"""

import os
import shutil
from pathlib import Path
from typing import Optional

from loguru import logger

from config import UPLOAD_DIR, MAX_FILE_SIZE_MB, ALLOWED_EXTENSIONS


def ensure_upload_dir() -> Path:
    """Create the upload directory if it doesn't exist."""
    upload_path = Path(UPLOAD_DIR)
    upload_path.mkdir(parents=True, exist_ok=True)
    return upload_path


def validate_file(filename: str, file_size_bytes: int) -> tuple[bool, str]:
    """
    Validate uploaded file by extension and size.
    Returns (is_valid, error_message).
    """
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Invalid file type '{ext}'. Allowed: {ALLOWED_EXTENSIONS}"

    max_bytes = MAX_FILE_SIZE_MB * 1024 * 1024
    if file_size_bytes > max_bytes:
        return False, f"File too large ({file_size_bytes / 1024 / 1024:.1f} MB). Max: {MAX_FILE_SIZE_MB} MB"

    return True, ""


def save_uploaded_file(filename: str, file_content: bytes) -> Path:
    """
    Save uploaded PDF to the uploads directory.
    Returns the path to the saved file.
    """
    upload_dir = ensure_upload_dir()
    file_path = upload_dir / filename

    # Avoid overwriting — add suffix if file exists
    counter = 1
    while file_path.exists():
        stem = Path(filename).stem
        ext = Path(filename).suffix
        file_path = upload_dir / f"{stem}_{counter}{ext}"
        counter += 1

    file_path.write_bytes(file_content)
    logger.info(f"Saved uploaded file: {file_path} ({len(file_content)} bytes)")
    return file_path


def get_page_count(file_path: str) -> int:
    """Get the number of pages in a PDF file."""
    from ingestion.pdf_utils import extract_page_count
    return extract_page_count(file_path)


def preprocess_document(file_path: str) -> dict:
    """
    Preprocess a PDF document — extract text and metadata.
    Returns a dict with text content, page count, and file info.
    """
    from ingestion.pdf_utils import extract_text_from_pdf, extract_page_count

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {file_path}")

    page_count = extract_page_count(file_path)
    text_by_page = extract_text_from_pdf(file_path)
    full_text = "\n\n".join(text_by_page)

    result = {
        "filename": path.name,
        "file_path": str(path.absolute()),
        "file_size_bytes": path.stat().st_size,
        "page_count": page_count,
        "text_by_page": text_by_page,
        "full_text": full_text,
        "has_text": len(full_text.strip()) > 0,
    }

    logger.info(
        f"Preprocessed '{path.name}': {page_count} pages, "
        f"{len(full_text)} chars, has_text={result['has_text']}"
    )
    return result


def detect_document_type(text: str) -> str:
    """
    Auto-detect document type from extracted text.
    Returns: 'invoice', 'tax_1040', 'insurance_claim', or 'unknown'
    """
    text_lower = text.lower()

    # IRS 1040 indicators
    tax_keywords = ["form 1040", "internal revenue", "irs", "taxable income",
                     "adjusted gross income", "filing status", "w-2", "tax return"]
    tax_score = sum(1 for kw in tax_keywords if kw in text_lower)

    # Invoice indicators
    invoice_keywords = ["invoice", "bill to", "ship to", "subtotal", "total due",
                        "payment terms", "invoice number", "inv#", "purchase order"]
    invoice_score = sum(1 for kw in invoice_keywords if kw in text_lower)

    # Insurance claim indicators
    insurance_keywords = ["claim", "policy number", "insured", "deductible",
                          "coverage", "premium", "claimant", "loss date",
                          "insurance", "benefit"]
    insurance_score = sum(1 for kw in insurance_keywords if kw in text_lower)

    scores = {
        "invoice": invoice_score,
        "tax_1040": tax_score,
        "insurance_claim": insurance_score,
    }

    best_type = max(scores, key=scores.get)
    if scores[best_type] < 2:
        return "unknown"

    logger.info(f"Detected document type: {best_type} (scores: {scores})")
    return best_type

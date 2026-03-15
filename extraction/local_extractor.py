"""
Local Extractor — Pure local fallback using regex on raw PDF text.
No API key required. No external service.
Activates only when HyperAPI returns null/empty fields.
"""

import re
import pdfplumber
from loguru import logger


class LocalExtractor:
    """
    Pure local fallback using regex on raw PDF text.
    No API key required. No external service.
    Activates only when HyperAPI returns null/empty fields.
    """

    PATTERNS = {
        "total_amount":   r'(?:total|amount due|grand total)[^\d]*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
        "subtotal":       r'(?:subtotal|sub-total)[^\d]*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
        "tax_amount":     r'(?:tax|gst|vat)[^\d]*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)',
        "tax_rate":       r'(?:tax rate|vat rate|gst rate)[^\d]*(\d{1,3}(?:\.\d{1,4})?)\s*%?',
        "invoice_number": r'(?:invoice\s*#?|inv\s*#?)[^\w]*([A-Z0-9\-]+)',
        "invoice_date":   r'(?:invoice date|date)[^\d]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})',
        "due_date":       r'(?:due date|payment due)[^\d]*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})',
        "vendor_name":    r'^([A-Z][A-Za-z\s]+(?:Ltd|Inc|Corp|LLC|Co)\.?)',
        "claim_number":   r'(?:claim\s*#?|claim number)[^\w]*([A-Z0-9\-]+)',
        "policy_number":  r'(?:policy\s*#?|policy number)[^\w]*([A-Z0-9\-]+)',
        "tax_year":       r'(?:tax year|year)[^\d]*(20\d{2})',
        "filing_status":  r'(?:filing status)[^\w]*(single|married|head of household)',
    }

    def extract(self, pdf_path: str, doc_type: str) -> dict:
        logger.info(f"[LOCAL] Running regex fallback on {pdf_path}")
        text = self._get_text(pdf_path)
        results = {}
        for field, pattern in self.PATTERNS.items():
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            results[field] = {
                "value": match.group(1).strip() if match else None,
                "confidence": 0.72 if match else 0.0,
                "source": "local_regex"
            }
        return results

    def _get_text(self, pdf_path: str) -> str:
        text = ""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() or ""
        except Exception as e:
            logger.error(f"PDF text extraction failed: {e}")
        return text

    def fill_gaps(self, hyper_results: dict, pdf_path: str, doc_type: str) -> dict:
        """
        Only fills fields that HyperAPI returned as None or empty.
        Never overwrites what HyperAPI already found.
        """
        local_results = self.extract(pdf_path, doc_type)
        filled = hyper_results.copy()
        gaps_filled = 0
        for field, data in local_results.items():
            existing = hyper_results.get(field, {})
            existing_value = existing.get("value") if isinstance(existing, dict) else existing
            if (existing_value is None or existing_value == "") and data["value"] is not None:
                filled[field] = data
                gaps_filled += 1
                logger.info(f"[LOCAL] Filled gap: {field} = {data['value']}")
        logger.info(f"[LOCAL] Filled {gaps_filled} gaps from HyperAPI extraction")
        return filled

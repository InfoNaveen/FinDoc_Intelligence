"""
STEP 1: Extract all 1000 pages from gauntlet.pdf into SQLite.
Run: python gauntlet/extract_pages.py
"""

import PyPDF2
import sqlite3
import re
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def setup_db(db_path="gauntlet.db"):
    conn = sqlite3.connect(db_path)
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS pages (
            page_num    INTEGER PRIMARY KEY,
            raw_text    TEXT,
            doc_type    TEXT,
            doc_id      TEXT
        );
        CREATE TABLE IF NOT EXISTS documents (
            doc_id      TEXT PRIMARY KEY,
            doc_type    TEXT,
            start_page  INTEGER,
            end_page    INTEGER,
            vendor_name TEXT,
            vendor_gstin TEXT,
            vendor_ifsc TEXT,
            invoice_date TEXT,
            po_reference TEXT,
            subtotal    REAL,
            cgst        REAL,
            sgst        REAL,
            grand_total REAL
        );
        CREATE TABLE IF NOT EXISTS findings (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            finding_id  TEXT,
            category    TEXT,
            pages       TEXT,
            doc_refs    TEXT,
            description TEXT,
            reported_value TEXT,
            correct_value  TEXT,
            source      TEXT DEFAULT 'rule'
        );
    ''')
    conn.commit()
    return conn


def detect_doc_type(text):
    t = text.upper()
    if 'TAX INVOICE' in t:       return 'invoice'
    if 'PURCHASE ORDER' in t:    return 'purchase_order'
    if 'BANK STATEMENT' in t:    return 'bank_statement'
    if 'EXPENSE REPORT' in t:    return 'expense_report'
    if 'CREDIT NOTE' in t:       return 'credit_note'
    if 'DEBIT NOTE' in t:        return 'debit_note'
    if 'DELIVERY NOTE' in t:     return 'delivery_note'
    if 'QUOTATION' in t:         return 'quotation'
    if 'RECEIPT' in t:           return 'receipt'
    return 'unknown'


def extract_doc_id(text):
    patterns = [
        r'(INV-\d{4}-\d+)',
        r'(PO-\d{4}-\d+)',
        r'(EXP-\d{4}-\d+)',
        r'(CN-\d{4}-\d+)',
        r'(DN-\d{4}-\d+)',
        r'(BS-\d{4}-\d+)',
        r'(REC-\d{4}-\d+)',
        r'(QT-\d{4}-\d+)',
    ]
    for p in patterns:
        m = re.search(p, text)
        if m:
            return m.group(1)
    return None


def extract_all(pdf_path="gauntlet.pdf", db_path="gauntlet.db"):
    if not os.path.exists(pdf_path):
        print(f"ERROR: {pdf_path} not found. Copy gauntlet.pdf to project root.")
        return

    conn = setup_db(db_path)

    with open(pdf_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        total = len(reader.pages)
        print(f"Total pages: {total}")

        for i in range(total):
            text = reader.pages[i].extract_text() or ""
            doc_type = detect_doc_type(text)
            doc_id = extract_doc_id(text)

            conn.execute(
                'INSERT OR REPLACE INTO pages VALUES (?,?,?,?)',
                (i + 1, text, doc_type, doc_id)
            )

            if (i + 1) % 100 == 0:
                conn.commit()
                print(f"  Processed {i+1}/{total} pages")

    conn.commit()
    conn.close()
    print(f"Done. All {total} pages stored in {db_path}")


if __name__ == "__main__":
    extract_all()

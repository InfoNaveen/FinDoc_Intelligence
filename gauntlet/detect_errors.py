"""
STEP 2: Find all errors in gauntlet.pdf pages.
Run: python gauntlet/detect_errors.py
"""

import sqlite3
import re
import json
import sys
import os
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gauntlet.vendor_master import VENDOR_MASTER, REGISTERED_VENDORS, STATE_CODES, HSN_GST_RATES
from extraction.bedrock_client import BedrockStructurer

conn = sqlite3.connect("gauntlet.db")
findings = []
fid = 1
bedrock = BedrockStructurer()


def add(category, pages, doc_refs, description, reported, correct):
    global fid
    findings.append({
        "finding_id": f"F-{fid:03d}",
        "category": category,
        "pages": pages if isinstance(pages, list) else [pages],
        "document_refs": doc_refs if isinstance(doc_refs, list) else [doc_refs],
        "description": description,
        "reported_value": str(reported),
        "correct_value": str(correct)
    })
    fid += 1
    print(f"  [{fid-1:03d}] {category} | {doc_refs} | p{pages} | {reported} → {correct}")


def clean_num(s):
    if s is None: return None
    s = re.sub(r'[■₹,\s]', '', str(s))
    try: return Decimal(s)
    except: return None


def is_valid_date(date_str):
    for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%m/%d/%Y']:
        try:
            datetime.strptime(date_str.strip(), fmt)
            return True, ""
        except ValueError as e:
            pass
    # Check impossible days manually
    m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', date_str)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if day == 0: return False, "Day 0 is invalid"
        if day > 31: return False, f"Day {day} exceeds 31"
        if month == 0 or month > 12: return False, f"Month {month} invalid"
        try:
            datetime(year, month, day)
        except ValueError as e:
            return False, str(e)
    return True, ""


def similarity_score(a, b):
    a, b = a.lower().strip(), b.lower().strip()
    if a == b: return 1.0
    if not a or not b: return 0.0
    longer = max(len(a), len(b))
    matches = sum(c in b for c in a)
    return matches / longer


# ============================================================
# RULE-BASED CHECKS
# ============================================================

print("\n" + "="*60)
print("STARTING ERROR DETECTION")
print("="*60)

all_pages = conn.execute(
    "SELECT page_num, doc_id, doc_type, raw_text FROM pages WHERE page_num > 4"
).fetchall()

invoice_pages = [(p, d, t) for p, d, dt, t in all_pages if dt == 'invoice' and d]
bank_pages    = [(p, d, t) for p, d, dt, t in all_pages if dt == 'bank_statement' and d]
expense_pages = [(p, d, t) for p, d, dt, t in all_pages if dt == 'expense_report' and d]
po_pages      = [(p, d, t) for p, d, dt, t in all_pages if dt == 'purchase_order' and d]

# --------------------------------------------------
# CHECK 1: ARITHMETIC ERRORS (12 needles, 1pt each)
# --------------------------------------------------
print("\n[1] Checking arithmetic errors...")
for page_num, doc_id, text in invoice_pages:
    lines = text.split('\n')
    line_totals = []
    for line in lines:
        m = re.search(
            r'^\s*\d+\s+.{5,50}\s+\d+\s+([\d.]+)\s+\w+\s+[■₹]?([\d,]+\.?\d*)\s+[■₹]?([\d,]+\.?\d*)',
            line
        )
        if m:
            qty = clean_num(m.group(1))
            rate = clean_num(m.group(2))
            amount = clean_num(m.group(3))
            if qty and rate and amount:
                calc = (qty * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                diff = abs(calc - amount)
                if diff > Decimal('1.00'):
                    add("arithmetic_error", [page_num], [doc_id],
                        f"{qty}×{rate}={calc} but shows {amount}",
                        str(amount), str(calc))
                else:
                    line_totals.append(amount)

    # Check subtotal vs sum of lines
    subtotal_match = re.search(r'Subtotal[:\s]+[■₹]?([\d,]+\.?\d*)', text)
    if subtotal_match and line_totals:
        reported_sub = clean_num(subtotal_match.group(1))
        calc_sub = sum(line_totals).quantize(Decimal('0.01'))
        if reported_sub and abs(reported_sub - calc_sub) > Decimal('1.00'):
            add("arithmetic_error", [page_num], [doc_id],
                f"Subtotal sum mismatch: lines sum to {calc_sub} but shows {reported_sub}",
                str(reported_sub), str(calc_sub))

    # Check grand total = subtotal + cgst + sgst
    gt_match  = re.search(r'GRAND TOTAL[:\s]+[■₹]?([\d,]+\.?\d*)', text, re.IGNORECASE)
    cgst_match = re.search(r'CGST[:\s]+[■₹]?([\d,]+\.?\d*)', text, re.IGNORECASE)
    sgst_match = re.search(r'SGST[:\s]+[■₹]?([\d,]+\.?\d*)', text, re.IGNORECASE)
    igst_match = re.search(r'IGST[:\s]+[■₹]?([\d,]+\.?\d*)', text, re.IGNORECASE)
    sub_match  = re.search(r'Subtotal[:\s]+[■₹]?([\d,]+\.?\d*)', text, re.IGNORECASE)
    if gt_match and sub_match:
        gt  = clean_num(gt_match.group(1))
        sub = clean_num(sub_match.group(1))
        cgst = clean_num(cgst_match.group(1)) if cgst_match else Decimal('0')
        sgst = clean_num(sgst_match.group(1)) if sgst_match else Decimal('0')
        igst = clean_num(igst_match.group(1)) if igst_match else Decimal('0')
        if gt and sub:
            calc_gt = (sub + cgst + sgst + igst).quantize(Decimal('0.01'))
            if abs(gt - calc_gt) > Decimal('1.00'):
                add("arithmetic_error", [page_num], [doc_id],
                    f"Grand total mismatch: {sub}+tax={calc_gt} but shows {gt}",
                    str(gt), str(calc_gt))

# --------------------------------------------------
# CHECK 2: INVALID DATES (10 needles, 1pt each)
# --------------------------------------------------
print("\n[2] Checking invalid dates...")
for page_num, doc_id, doc_type, text in all_pages:
    if not doc_id: continue
    date_matches = re.findall(r'\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})\b', text)
    for date_str in date_matches:
        valid, reason = is_valid_date(date_str)
        if not valid:
            add("invalid_date", [page_num], [doc_id],
                f"Invalid date {date_str}: {reason}",
                date_str, "Valid calendar date")

# --------------------------------------------------
# CHECK 3: FAKE VENDOR (10 needles, 7pts each)
# --------------------------------------------------
print("\n[3] Checking fake vendors...")
for page_num, doc_id, text in invoice_pages:
    vendor_match = re.search(
        r'(?:VENDOR DETAILS|Vendor|Supplier|Name)[:\s\n]+([A-Z][A-Za-z\s&\.\-]+(?:Ltd|Inc|Pvt|Corp|LLP|Limited)\.?)',
        text
    )
    if vendor_match:
        found = vendor_match.group(1).strip()
        in_master = found in REGISTERED_VENDORS
        close = any(similarity_score(found, v) > 0.85 for v in REGISTERED_VENDORS)
        if not in_master and not close:
            add("fake_vendor", [page_num], [doc_id],
                f"'{found}' not in Vendor Master",
                found, "Must be registered vendor")

# --------------------------------------------------
# CHECK 4: GSTIN STATE MISMATCH (5 needles, 3pts each)
# --------------------------------------------------
print("\n[4] Checking GSTIN state mismatches...")
for page_num, doc_id, text in invoice_pages:
    gstin_m = re.search(r'GSTIN[:\s]+([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])', text)
    addr_m  = re.search(r'Address[:\s]+.+?,\s+([A-Za-z\s]+)\s*-\s*\d{6}', text)
    if gstin_m and addr_m:
        gstin = gstin_m.group(1)
        state_code = gstin[:2]
        addr_state = addr_m.group(1).strip()
        expected = STATE_CODES.get(state_code, "")
        if expected and expected.lower() not in addr_state.lower() \
                and addr_state.lower() not in expected.lower():
            add("gstin_state_mismatch", [page_num], [doc_id],
                f"GSTIN {state_code}={expected} but address says {addr_state}",
                f"{state_code}→{addr_state}", f"{state_code}→{expected}")

# --------------------------------------------------
# CHECK 5: IFSC MISMATCH (5 needles, 3pts each)
# --------------------------------------------------
print("\n[5] Checking IFSC mismatches...")
for page_num, doc_id, text in invoice_pages:
    for vendor_name, master in VENDOR_MASTER.items():
        if vendor_name in text:
            ifsc_m = re.search(r'IFSC[:\s]+([A-Z]{4}0[A-Z0-9]{6})', text)
            if ifsc_m and master.get("ifsc"):
                found_ifsc = ifsc_m.group(1)
                if found_ifsc != master["ifsc"]:
                    add("ifsc_mismatch", [page_num], [doc_id],
                        f"IFSC {found_ifsc} ≠ master {master['ifsc']} for {vendor_name}",
                        found_ifsc, master["ifsc"])

# --------------------------------------------------
# CHECK 6: VENDOR NAME TYPO (10 needles, 3pts each)
# --------------------------------------------------
print("\n[6] Checking vendor name typos...")
for page_num, doc_id, text in invoice_pages:
    vendor_match = re.search(
        r'(?:Name|Vendor)[:\s]+([A-Z][A-Za-z\s&\.]+(?:Ltd|Inc|Pvt|Corp|LLP)\.?)',
        text
    )
    if vendor_match:
        found = vendor_match.group(1).strip()
        if found in REGISTERED_VENDORS:
            continue
        for master_name in REGISTERED_VENDORS:
            score = similarity_score(found, master_name)
            if 0.75 < score < 0.97:
                add("vendor_name_typo", [page_num], [doc_id],
                    f"'{found}' is likely typo of '{master_name}'",
                    found, master_name)
                break

# --------------------------------------------------
# CHECK 7: DUPLICATE LINE ITEMS (4 needles, 1pt each)
# --------------------------------------------------
print("\n[7] Checking duplicate line items...")
invoice_line_map = {}
for page_num, doc_id, text in invoice_pages:
    if doc_id not in invoice_line_map:
        invoice_line_map[doc_id] = {"lines": [], "pages": []}
    invoice_line_map[doc_id]["pages"].append(page_num)
    for line in text.split('\n'):
        m = re.search(r'^\s*\d+\s+(.{10,50})\s+\d+\s+[\d.]+', line)
        if m:
            invoice_line_map[doc_id]["lines"].append(m.group(1).strip()[:40])

for doc_id, data in invoice_line_map.items():
    seen = {}
    for line in data["lines"]:
        seen[line] = seen.get(line, 0) + 1
    for line, count in seen.items():
        if count > 1:
            add("duplicate_line_item", data["pages"][:1], [doc_id],
                f"'{line[:30]}' appears {count} times",
                f"Count: {count}", "Count: 1")

# --------------------------------------------------
# CHECK 8: DATE CASCADE (5 needles, 3pts each)
# Invoice date before its own PO date
# --------------------------------------------------
print("\n[8] Checking date cascades...")
po_dates = {}
for page_num, doc_id, text in po_pages:
    date_m = re.search(r'(?:Date|PO Date)[:\s]+(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})', text)
    if date_m:
        try:
            po_dates[doc_id] = datetime.strptime(date_m.group(1), '%d/%m/%Y')
        except: pass

for page_num, doc_id, text in invoice_pages:
    po_ref_m = re.search(r'PO[- ]?(?:Reference|Ref|No\.?)[:\s]+(PO-\d{4}-\d+)', text)
    inv_date_m = re.search(r'(?:Invoice )?Date[:\s]+(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})', text)
    if po_ref_m and inv_date_m:
        po_ref = po_ref_m.group(1)
        try:
            inv_date = datetime.strptime(inv_date_m.group(1), '%d/%m/%Y')
            if po_ref in po_dates and inv_date < po_dates[po_ref]:
                add("date_cascade", [page_num], [doc_id],
                    f"Invoice date {inv_date_m.group(1)} is before PO date {po_dates[po_ref].strftime('%d/%m/%Y')}",
                    inv_date_m.group(1), f"After {po_dates[po_ref].strftime('%d/%m/%Y')}")
        except: pass

# --------------------------------------------------
# CHECK 9: BALANCE DRIFT (15 needles, 7pts each)
# Opening balance ≠ previous month closing
# --------------------------------------------------
print("\n[9] Checking bank balance drift...")
bank_data = {}
for page_num, doc_id, text in bank_pages:
    open_m  = re.search(r'Opening Balance[:\s]+[■₹]?([\d,]+\.?\d*)', text, re.IGNORECASE)
    close_m = re.search(r'Closing Balance[:\s]+[■₹]?([\d,]+\.?\d*)', text, re.IGNORECASE)
    month_m = re.search(r'(?:Statement for|Month)[:\s]+([A-Za-z]+\s+\d{4})', text)
    if open_m and close_m:
        bank_data[doc_id] = {
            "page": page_num,
            "opening": clean_num(open_m.group(1)),
            "closing": clean_num(close_m.group(1)),
            "month": month_m.group(1) if month_m else ""
        }

sorted_banks = sorted(bank_data.items(), key=lambda x: x[1].get("month", ""))
for i in range(1, len(sorted_banks)):
    prev_id, prev = sorted_banks[i-1]
    curr_id, curr = sorted_banks[i]
    if prev["closing"] and curr["opening"]:
        if abs(prev["closing"] - curr["opening"]) > Decimal("0.01"):
            add("balance_drift",
                [curr["page"]], [curr_id],
                f"Opening {curr['opening']} ≠ previous closing {prev['closing']}",
                str(curr["opening"]), str(prev["closing"]))

# --------------------------------------------------
# CHECK 10: PHANTOM PO REFERENCE (5 needles, 7pts each)
# --------------------------------------------------
print("\n[10] Checking phantom PO references...")
valid_po_ids = {doc_id for _, doc_id, _ in po_pages}
for page_num, doc_id, text in invoice_pages:
    po_ref_m = re.search(r'PO[- ]?(?:Reference|Ref|No\.?)[:\s]+(PO-\d{4}-\d+)', text)
    if po_ref_m:
        cited_po = po_ref_m.group(1)
        if cited_po not in valid_po_ids:
            add("phantom_po_reference", [page_num], [doc_id],
                f"Invoice cites {cited_po} which doesn't exist in dataset",
                cited_po, "Must reference existing PO")

# --------------------------------------------------
# CHECK 11: BEDROCK AI ANALYSIS (catch what rules miss)
# --------------------------------------------------
print("\n[11] Running Bedrock AI analysis on invoices...")
analyzed = 0
for page_num, doc_id, text in invoice_pages[:50]:  # limit to 50 for time
    if len(text) < 200: continue
    try:
        ai_findings = bedrock.analyze_for_errors(text, doc_id)
        for f in ai_findings:
            if f.get("category") and f.get("reported_value"):
                # Only add if not already found by rules
                already_found = any(
                    x["category"] == f["category"] and
                    doc_id in x["document_refs"]
                    for x in findings
                )
                if not already_found:
                    add(f["category"], [page_num], [doc_id],
                        f.get("description", "AI detected error"),
                        f.get("reported_value", ""),
                        f.get("correct_value", ""))
        analyzed += 1
    except Exception as e:
        pass

print(f"  Bedrock analyzed {analyzed} invoices")

# ============================================================
# SAVE RESULTS
# ============================================================
conn.close()

result = {
    "team_id": "apex_null",
    "findings": findings
}

with open("submission.json", "w") as f:
    json.dump(result, f, indent=2)

print(f"\n{'='*60}")
print(f"TOTAL FINDINGS: {len(findings)}")
print(f"Saved → submission.json")
print(f"{'='*60}")

# Category breakdown
from collections import Counter
cats = Counter(f["category"] for f in findings)
for cat, count in sorted(cats.items()):
    print(f"  {cat}: {count}")

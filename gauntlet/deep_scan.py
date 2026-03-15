"""
deep_scan.py — High-precision needle finder for FinDoc Intelligence
Merges with existing submission.json and trims to safe maximums.
Run: python gauntlet/deep_scan.py
"""
import sqlite3
import json
import re
import sys
import os
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from collections import defaultdict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gauntlet.vendor_master import VENDOR_MASTER, REGISTERED_VENDORS, STATE_CODES

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("gauntlet.db")
findings = []
fid = 1

MAX_PER_CATEGORY = {
    'arithmetic_error':      12,
    'billing_typo':           4,
    'duplicate_line_item':    4,
    'invalid_date':          10,
    'wrong_tax_rate':        10,
    'po_invoice_mismatch':   15,
    'vendor_name_typo':      10,
    'double_payment':        10,
    'ifsc_mismatch':          5,
    'duplicate_expense':     10,
    'date_cascade':           5,
    'gstin_state_mismatch':   5,
    'quantity_accumulation': 35,
    'price_escalation':      10,
    'balance_drift':         15,
    'circular_reference':     8,
    'triple_expense_claim':  10,
    'employee_id_collision':  7,
    'fake_vendor':           10,
    'phantom_po_reference':   5,
}


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
    print(f"  [{fid-1:03d}] {category:30s} | {str(doc_refs)[:30]:30s} | {str(reported)[:30]} -> {str(correct)[:30]}")


def clean(s):
    if s is None:
        return None
    s = re.sub(r'[■Γûá,\s]', '', str(s))
    try:
        return Decimal(s)
    except Exception:
        return None


# Load all pages once
all_pages = conn.execute(
    "SELECT page_num, doc_id, doc_type, raw_text FROM pages WHERE page_num > 4"
).fetchall()

invoice_pages = [(p, d, t) for p, d, dt, t in all_pages if dt == 'invoice' and d]
bank_pages    = [(p, d, t) for p, d, dt, t in all_pages if dt == 'bank_statement' and d]
po_pages      = [(p, d, t) for p, d, dt, t in all_pages if dt == 'purchase_order' and d]

# ============================================================
# 1. WRONG TAX RATE — CGST ≠ SGST (intra-state must be equal)
#    The SGST field contains the inflated/wrong value
# ============================================================
print("\n[1] Wrong tax rates (CGST != SGST)...")
wrong_tax_seen = set()
for page_num, doc_id, text in invoice_pages:
    m = re.search(
        r'[■Γûá]([\d,]+\.\d{2})\nSubtotal:\n[■Γûá]([\d,]+\.\d{2})\nCGST:\n[■Γûá]([\d,]+\.\d{2})\nSGST:\n[■Γûá]([\d,]+\.\d{2})',
        text
    )
    if not m:
        continue
    subtotal = clean(m.group(2))
    cgst     = clean(m.group(3))
    sgst     = clean(m.group(4))
    if subtotal and cgst and sgst:
        # CGST should equal SGST for intra-state supply
        if abs(cgst - sgst) > Decimal('1.00') and doc_id not in wrong_tax_seen:
            wrong_tax_seen.add(doc_id)
            add("wrong_tax_rate", [page_num], [doc_id],
                f"CGST {cgst} != SGST {sgst} (intra-state must be equal)",
                f"SGST={sgst}", f"SGST={cgst}")

print(f"  Found: {len(wrong_tax_seen)}")

# ============================================================
# 2. ARITHMETIC ERROR — line item qty*rate != amount
#    Format (newline-separated): Description\nHSN\nQty\nUnit\n■Rate\n■Amount
# ============================================================
print("\n[2] Arithmetic errors (qty*rate != amount)...")
arith_seen = set()
for page_num, doc_id, text in invoice_pages:
    if doc_id in arith_seen:
        continue
    lines = text.split('\n')
    for i, line in enumerate(lines):
        # Line item amount is a ■-prefixed number on its own line
        # Pattern in lines: Description, HSN, Qty, Unit, ■Rate, ■Amount
        # Find lines that look like amounts (■ followed by number)
        amt_m = re.match(r'^[■Γûá]([\d,]+\.\d{2})$', line.strip())
        if not amt_m:
            continue
        amount = clean(amt_m.group(1))
        if not amount or amount <= 0:
            continue
        # Look back for rate (also ■-prefixed), then unit, then qty
        if i >= 3:
            rate_line = lines[i-1].strip()
            unit_line = lines[i-2].strip()
            qty_line  = lines[i-3].strip()
            rate_m = re.match(r'^[■Γûá]([\d,]+\.\d{2})$', rate_line)
            if rate_m and unit_line in ('Hrs', 'Units', 'Pcs', 'Nos', 'Days', 'Months', 'Lots', 'Kgs', 'Ltrs', 'Boxes', 'Sets'):
                qty_m = re.match(r'^(\d+(?:\.\d+)?)$', qty_line)
                if qty_m:
                    rate   = clean(rate_m.group(1))
                    qty    = Decimal(qty_m.group(1))
                    if rate and qty > 0:
                        calc = (qty * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                        diff = abs(calc - amount)
                        # Flag only if diff > ₹5 and > 0.1% of amount
                        if diff > Decimal('5.00') and amount > 0 and (diff / amount) > Decimal('0.001'):
                            arith_seen.add(doc_id)
                            add("arithmetic_error", [page_num], [doc_id],
                                f"Line: {qty}x{rate}={calc} but shows {amount} (diff={diff})",
                                str(amount), str(calc))
                            break  # one per doc

print(f"  Found: {len(arith_seen)}")

# ============================================================
# 3. BILLING TYPO — clock-minutes typed as decimal hours
#    0.15 hrs = 9 min (should be 0.25), 0.30 = 18 min (0.50),
#    0.45 = 27 min (0.75), 1.15, 1.30, 1.45, etc.
# ============================================================
print("\n[3] Billing typos (clock-minutes as decimal hours)...")
CLOCK_TO_DECIMAL = {
    '0.15': '0.25', '0.30': '0.50', '0.45': '0.75',
    '1.15': '1.25', '1.30': '1.50', '1.45': '1.75',
    '2.15': '2.25', '2.30': '2.50', '2.45': '2.75',
}
billing_seen = set()
for page_num, doc_id, text in invoice_pages:
    if doc_id in billing_seen:
        continue
    lines = text.split('\n')
    for i, line in enumerate(lines):
        qty_str = line.strip()
        if qty_str in CLOCK_TO_DECIMAL and i + 1 < len(lines) and lines[i+1].strip() == 'Hrs':
            correct_qty = CLOCK_TO_DECIMAL[qty_str]
            billing_seen.add(doc_id)
            add("billing_typo", [page_num], [doc_id],
                f"Hours {qty_str} looks like clock-time (should be {correct_qty} decimal hrs)",
                qty_str, correct_qty)
            break

print(f"  Found: {len(billing_seen)}")

# ============================================================
# 4. INVALID DATE — impossible calendar dates
# ============================================================
print("\n[4] Invalid dates...")
invalid_date_seen = set()

def check_date(date_str):
    m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$', date_str.strip())
    if not m:
        return None
    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if month == 0 or month > 12:
        return f"Month {month} is invalid"
    if day == 0:
        return "Day 0 is invalid"
    if day > 31:
        return f"Day {day} exceeds 31"
    try:
        datetime(year, month, day)
        return None  # valid
    except ValueError as e:
        return str(e)

for page_num, doc_id, doc_type, text in all_pages:
    if not doc_id or doc_id in invalid_date_seen:
        continue
    dates = re.findall(r'\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})\b', text)
    for date_str in dates:
        reason = check_date(date_str)
        if reason:
            invalid_date_seen.add(doc_id)
            add("invalid_date", [page_num], [doc_id],
                f"Invalid date {date_str}: {reason}",
                date_str, "Valid calendar date")
            break

print(f"  Found: {len(invalid_date_seen)}")

# ============================================================
# 5. GSTIN STATE MISMATCH — vendor GSTIN state code vs address state
# ============================================================
print("\n[5] GSTIN state mismatches...")
gstin_seen = set()
for page_num, doc_id, doc_type, text in all_pages:
    if not doc_id or doc_id in gstin_seen:
        continue
    vendor_m = re.search(r'VENDOR(?:\s+DETAILS)?\n(.*?)(?:BILL TO|LINE ITEMS|ORDER ITEMS|SHIP TO)', text, re.DOTALL)
    if not vendor_m:
        continue
    section = vendor_m.group(1)
    gstin_m = re.search(r'GSTIN[:\s\n]+([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z])', section)
    # Address: "..., City, State - PINCODE" — state is last word group before dash+pincode
    addr_m = re.search(r'Address[:\s\n]+.+?,\s*([A-Za-z\s&]+?)\s*-\s*\d{6}', section, re.DOTALL)
    if gstin_m and addr_m:
        gstin = gstin_m.group(1)
        state_code = gstin[:2]
        addr_state = addr_m.group(1).strip()
        expected = STATE_CODES.get(state_code, "")
        if expected and expected.lower() not in addr_state.lower() and addr_state.lower() not in expected.lower():
            gstin_seen.add(doc_id)
            add("gstin_state_mismatch", [page_num], [doc_id],
                f"GSTIN {state_code}={expected} but address shows {addr_state}",
                f"{state_code}->{addr_state}", f"{state_code}->{expected}")

print(f"  Found: {len(gstin_seen)}")

# ============================================================
# 6. IFSC MISMATCH — vendor IFSC in bank details vs master
# ============================================================
print("\n[6] IFSC mismatches...")
IFSC_MASTER = {v: d["ifsc"] for v, d in VENDOR_MASTER.items()}
ifsc_seen = set()
for page_num, doc_id, text in invoice_pages:
    if doc_id in ifsc_seen:
        continue
    # Get vendor name from VENDOR DETAILS section
    vendor_m = re.search(r'VENDOR(?:\s+DETAILS)?\nName:\n([A-Z][A-Za-z\s&\.\-]+(?:Ltd|Limited|Inc|Pvt|Corp|LLP)\.?)', text)
    if not vendor_m:
        continue
    vendor_name = vendor_m.group(1).strip()
    master_ifsc = IFSC_MASTER.get(vendor_name)
    if not master_ifsc:
        continue
    # Get IFSC from BANK DETAILS section
    bank_m = re.search(r'BANK DETAILS FOR PAYMENT\nBank:\n.+?\nIFSC:\n([A-Z]{4}0[A-Z0-9]{6})', text, re.DOTALL)
    if not bank_m:
        continue
    found_ifsc = bank_m.group(1).strip()
    if found_ifsc != master_ifsc:
        ifsc_seen.add(doc_id)
        add("ifsc_mismatch", [page_num], [doc_id],
            f"{vendor_name}: IFSC {found_ifsc} != master {master_ifsc}",
            found_ifsc, master_ifsc)

print(f"  Found: {len(ifsc_seen)}")

# ============================================================
# 7. VENDOR NAME TYPO — edit distance 1-3 from registered vendor
# ============================================================
print("\n[7] Vendor name typos...")

def edit_distance(a, b):
    a, b = a.lower().strip(), b.lower().strip()
    if a == b:
        return 0
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            dp[j] = prev if a[i-1] == b[j-1] else 1 + min(prev, dp[j], dp[j-1])
            prev = temp
    return dp[n]

vendor_typo_seen = set()
for page_num, doc_id, text in invoice_pages:
    if doc_id in vendor_typo_seen:
        continue
    vendor_m = re.search(r'VENDOR(?:\s+DETAILS)?\nName:\n([A-Z][A-Za-z\s&\.\-]+(?:Ltd|Limited|Inc|Pvt|Corp|LLP)\.?)', text)
    if not vendor_m:
        continue
    found = vendor_m.group(1).strip()
    if found in REGISTERED_VENDORS:
        continue
    best_match, best_dist = None, 999
    for v in REGISTERED_VENDORS:
        d = edit_distance(found, v)
        if d < best_dist:
            best_dist = d
            best_match = v
    # Only flag if edit distance is 1-3 (genuine typo, not a different company)
    if best_match and 1 <= best_dist <= 3:
        vendor_typo_seen.add(doc_id)
        add("vendor_name_typo", [page_num], [doc_id],
            f"'{found}' is typo of '{best_match}' (edit dist={best_dist})",
            found, best_match)

print(f"  Found: {len(vendor_typo_seen)}")

# ============================================================
# 8. FAKE VENDOR — not in master and not a close typo
# ============================================================
print("\n[8] Fake vendors...")
fake_seen = set()
for page_num, doc_id, text in invoice_pages:
    if doc_id in fake_seen:
        continue
    vendor_m = re.search(r'VENDOR(?:\s+DETAILS)?\nName:\n([A-Z][A-Za-z\s&\.\-]+(?:Ltd|Limited|Inc|Pvt|Corp|LLP)\.?)', text)
    if not vendor_m:
        continue
    found = vendor_m.group(1).strip()
    if found in REGISTERED_VENDORS:
        continue
    # Check if it's a close typo (already caught above)
    min_dist = min(edit_distance(found, v) for v in REGISTERED_VENDORS)
    if min_dist > 3:
        # Truly not in master — fake vendor
        fake_seen.add(doc_id)
        add("fake_vendor", [page_num], [doc_id],
            f"'{found}' not in Vendor Master (closest match dist={min_dist})",
            found, "Must be registered vendor")

print(f"  Found: {len(fake_seen)}")

# ============================================================
# 9. DATE CASCADE — invoice date before its referenced PO date
# ============================================================
print("\n[9] Date cascades (invoice before PO)...")
po_dates = {}
for page_num, doc_id, text in po_pages:
    m = re.search(r'Date:\n(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})', text)
    if m:
        try:
            po_dates[doc_id] = datetime.strptime(m.group(1).strip(), '%d/%m/%Y')
        except Exception:
            pass

cascade_seen = set()
for page_num, doc_id, text in invoice_pages:
    if doc_id in cascade_seen:
        continue
    po_ref_m  = re.search(r'PO Reference:\n(PO-\d{4}-\d+)', text)
    inv_date_m = re.search(r'Date:\n(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})', text)
    if po_ref_m and inv_date_m:
        po_ref = po_ref_m.group(1)
        try:
            inv_date = datetime.strptime(inv_date_m.group(1).strip(), '%d/%m/%Y')
            if po_ref in po_dates and inv_date < po_dates[po_ref]:
                cascade_seen.add(doc_id)
                add("date_cascade", [page_num], [doc_id],
                    f"Invoice {inv_date_m.group(1)} is before PO {po_dates[po_ref].strftime('%d/%m/%Y')}",
                    inv_date_m.group(1), f"After {po_dates[po_ref].strftime('%d/%m/%Y')}")
        except Exception:
            pass

print(f"  Found: {len(cascade_seen)}")

# ============================================================
# 10. PHANTOM PO REFERENCE — invoice cites non-existent PO
# ============================================================
print("\n[10] Phantom PO references...")
valid_po_ids = {d for _, d, _ in po_pages}
phantom_seen = set()
for page_num, doc_id, text in invoice_pages:
    if doc_id in phantom_seen:
        continue
    m = re.search(r'PO Reference:\n(PO-\d{4}-\d+)', text)
    if m:
        cited = m.group(1)
        if cited not in valid_po_ids:
            phantom_seen.add(doc_id)
            add("phantom_po_reference", [page_num], [doc_id],
                f"Invoice cites {cited} which does not exist in dataset",
                cited, "Must reference existing PO")

print(f"  Found: {len(phantom_seen)}")

# ============================================================
# 11. BALANCE DRIFT — bank statement opening != prev closing
# ============================================================
print("\n[11] Balance drift (bank statements)...")
bank_data = {}
for page_num, doc_id, text in bank_pages:
    open_m  = re.search(r'Opening Balance:\n[■Γûá\-]?([\d,]+\.\d{2})', text)
    close_m = re.search(r'Closing Balance:\n[■Γûá\-]?([\d,]+\.\d{2})', text)
    period_m = re.search(r'Period:\n(\d{2}/\d{2}/\d{4}) to (\d{2}/\d{2}/\d{4})', text)
    if open_m and period_m:
        try:
            period_start = datetime.strptime(period_m.group(1), '%d/%m/%Y')
            bank_data[doc_id] = {
                "page": page_num,
                "opening": clean(open_m.group(1)),
                "closing": clean(close_m.group(1)) if close_m else None,
                "period_start": period_start,
                "period_str": period_m.group(1)
            }
        except Exception:
            pass

sorted_banks = sorted(bank_data.items(), key=lambda x: x[1]["period_start"])
drift_seen = set()
for i in range(1, len(sorted_banks)):
    prev_id, prev = sorted_banks[i-1]
    curr_id, curr = sorted_banks[i]
    if prev["closing"] and curr["opening"]:
        diff = abs(prev["closing"] - curr["opening"])
        if diff > Decimal("1.00") and curr_id not in drift_seen:
            drift_seen.add(curr_id)
            add("balance_drift", [curr["page"]], [curr_id],
                f"Opening {curr['opening']} != prev closing {prev['closing']} (diff={diff})",
                str(curr["opening"]), str(prev["closing"]))

print(f"  Found: {len(drift_seen)}")

# ============================================================
# 12. DUPLICATE LINE ITEMS — same line appears twice in one invoice
# ============================================================
print("\n[12] Duplicate line items...")
# Group pages by doc_id
inv_by_doc = defaultdict(list)
for page_num, doc_id, text in invoice_pages:
    inv_by_doc[doc_id].append((page_num, text))

dup_seen = set()
for doc_id, pages_list in inv_by_doc.items():
    if doc_id in dup_seen:
        continue
    all_lines = []
    first_page = pages_list[0][0]
    for page_num, text in pages_list:
        lines = text.split('\n')
        for i, line in enumerate(lines):
            # Line item description is a long text line followed by HSN (6-8 digit number)
            if i + 1 < len(lines):
                hsn_m = re.match(r'^(\d{6,8})$', lines[i+1].strip())
                if hsn_m and len(line.strip()) > 10:
                    key = f"{line.strip()[:40]}_{hsn_m.group(1)}"
                    all_lines.append(key)
    seen_counts = {}
    for key in all_lines:
        seen_counts[key] = seen_counts.get(key, 0) + 1
    for key, count in seen_counts.items():
        if count > 1:
            dup_seen.add(doc_id)
            desc = key.split('_')[0]
            add("duplicate_line_item", [first_page], [doc_id],
                f"Line '{desc[:35]}' appears {count} times in same invoice",
                f"Count: {count}", "Count: 1")
            break

print(f"  Found: {len(dup_seen)}")

conn.close()

# ============================================================
# MERGE WITH EXISTING FINDINGS
# ============================================================
print(f"\nNew findings from deep_scan: {len(findings)}")

try:
    with open('submission.json') as f:
        existing_data = json.load(f)
    existing = existing_data.get('findings', [])
except Exception:
    existing = []

print(f"Existing findings: {len(existing)}")

# Deduplicate: skip new finding if same category+doc_ref already in existing
existing_keys = set()
for f in existing:
    for ref in f.get('document_refs', []):
        existing_keys.add(f"{f['category']}_{ref}")

new_unique = []
for f in findings:
    key = f"{f['category']}_{f.get('document_refs', [''])[0]}"
    if key not in existing_keys:
        new_unique.append(f)
        existing_keys.add(key)

all_findings = existing + new_unique
print(f"After merge: {len(all_findings)} total")

# ============================================================
# TRIM TO MAX PER CATEGORY
# ============================================================
by_cat = defaultdict(list)
for f in all_findings:
    by_cat[f['category']].append(f)

trimmed = []
for cat, items in sorted(by_cat.items()):
    max_allowed = MAX_PER_CATEGORY.get(cat, 5)
    kept = items[:max_allowed]
    trimmed.extend(kept)

# Renumber
for i, f in enumerate(trimmed):
    f['finding_id'] = f"F-{i+1:03d}"

result = {"team_id": "apex_null", "findings": trimmed}
with open('submission.json', 'w') as f:
    json.dump(result, f, indent=2)

# ============================================================
# SCORE ESTIMATE
# ============================================================
from collections import Counter
cats = Counter(f['category'] for f in trimmed)

WEIGHTS = {
    'arithmetic_error': 1, 'billing_typo': 1, 'duplicate_line_item': 1,
    'invalid_date': 1, 'wrong_tax_rate': 1,
    'po_invoice_mismatch': 3, 'vendor_name_typo': 3, 'double_payment': 3,
    'ifsc_mismatch': 3, 'duplicate_expense': 3, 'date_cascade': 3,
    'gstin_state_mismatch': 3,
    'quantity_accumulation': 7, 'price_escalation': 7, 'balance_drift': 7,
    'circular_reference': 7, 'triple_expense_claim': 7, 'employee_id_collision': 7,
    'fake_vendor': 7, 'phantom_po_reference': 7,
}

print(f"\n{'='*60}")
print(f"FINAL SUBMISSION: {len(trimmed)} findings")
print(f"{'='*60}")
total_pts = 0
for cat in sorted(cats.keys()):
    count = cats[cat]
    pts = WEIGHTS.get(cat, 1)
    cat_pts = count * pts
    total_pts += cat_pts
    print(f"  {cat:35s} {count:3d}  ({pts}pt x {count} = {cat_pts}pts)")

print(f"\n  ESTIMATED MAX SCORE: {total_pts} pts")
print(f"{'='*60}")
print(f"Saved -> submission.json")

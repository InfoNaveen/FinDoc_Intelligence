"""
detect_missing.py — Find the high-value categories not yet in submission.json
Merges new findings into submission.json and re-renumbers.
"""
import sqlite3
import re
import json
import sys
import os
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from collections import defaultdict, Counter

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gauntlet.vendor_master import VENDOR_MASTER, REGISTERED_VENDORS, STATE_CODES, HSN_GST_RATES

# Load existing submission
with open("submission.json") as f:
    data = json.load(f)

existing = data["findings"]
existing_refs = set()
for f in existing:
    for ref in f.get("document_refs", []):
        existing_refs.add((f["category"], ref))

new_findings = []

def add(category, pages, doc_refs, description, reported, correct):
    refs = doc_refs if isinstance(doc_refs, list) else [doc_refs]
    # Skip if we already have this category+document
    for ref in refs:
        if (category, ref) in existing_refs:
            return
    new_findings.append({
        "finding_id": "NEW",
        "category": category,
        "pages": pages if isinstance(pages, list) else [pages],
        "document_refs": refs,
        "description": description,
        "reported_value": str(reported),
        "correct_value": str(correct)
    })
    existing_refs.add((category, refs[0]))
    print(f"  [+] {category} | {refs} | {reported} → {correct}")


def clean_num(s):
    if s is None: return None
    s = re.sub(r'[■₹,\s]', '', str(s))
    try: return Decimal(s)
    except: return None


conn = sqlite3.connect("gauntlet.db")
all_pages = conn.execute(
    "SELECT page_num, doc_id, doc_type, raw_text FROM pages WHERE page_num > 4"
).fetchall()

invoice_pages = [(p, d, t) for p, d, dt, t in all_pages if dt == 'invoice' and d]
bank_pages    = [(p, d, t) for p, d, dt, t in all_pages if dt == 'bank_statement' and d]
expense_pages = [(p, d, t) for p, d, dt, t in all_pages if dt == 'expense_report' and d]
po_pages      = [(p, d, t) for p, d, dt, t in all_pages if dt == 'purchase_order' and d]

# ===================================================================
# 1. WRONG TAX RATE (10 needles, 1pt each)
# Check if GST % applied doesn't match HSN/SAC code standard rate
# ===================================================================
print("\n[A] Wrong tax rate...")
for page_num, doc_id, text in invoice_pages:
    hsn_m   = re.search(r'HSN[/\s]?(?:SAC)?[:\s]+(\d{4,8})', text)
    cgst_m  = re.search(r'CGST[:\s]+(\d+)%', text)
    sgst_m  = re.search(r'SGST[:\s]+(\d+)%', text)
    igst_m  = re.search(r'IGST[:\s]+(\d+)%', text)
    if hsn_m and (cgst_m or igst_m):
        hsn = hsn_m.group(1)
        applied_rate = int(cgst_m.group(1)) * 2 if cgst_m else int(igst_m.group(1))
        expected_rate = HSN_GST_RATES.get(hsn, HSN_GST_RATES.get(hsn[:4]))
        if expected_rate and applied_rate != expected_rate:
            add("wrong_tax_rate", [page_num], [doc_id],
                f"HSN {hsn}: applied GST {applied_rate}% but standard is {expected_rate}%",
                f"{applied_rate}%", f"{expected_rate}%")


# ===================================================================
# 2. PO-INVOICE MISMATCH (15 needles, 3pts each)
# PO has different amount/quantity than invoice
# ===================================================================
print("\n[B] PO–Invoice mismatch...")
po_data = {}
for page_num, doc_id, text in po_pages:
    amt_m = re.search(r'Total[:\s]+[■₹]?([\d,]+\.?\d*)', text, re.IGNORECASE)
    vendor_m = re.search(r'(?:Vendor|Supplier)[:\s]+([A-Z][A-Za-z\s&.]+(?:Ltd|Inc|Pvt|Corp|LLP)\.?)', text)
    if amt_m:
        po_data[doc_id] = {
            "page": page_num,
            "amount": clean_num(amt_m.group(1)),
            "vendor": vendor_m.group(1).strip() if vendor_m else ""
        }

for page_num, doc_id, text in invoice_pages:
    po_ref_m = re.search(r'PO[- ]?(?:Reference|Ref|No\.?)[:\s]+(PO-\d{4}-\d+)', text)
    inv_total_m = re.search(r'GRAND TOTAL[:\s]+[■₹]?([\d,]+\.?\d*)', text, re.IGNORECASE)
    if po_ref_m and inv_total_m:
        po_ref = po_ref_m.group(1)
        inv_total = clean_num(inv_total_m.group(1))
        if po_ref in po_data and po_data[po_ref]["amount"] and inv_total:
            diff = abs(po_data[po_ref]["amount"] - inv_total)
            pct = diff / po_data[po_ref]["amount"] * 100 if po_data[po_ref]["amount"] else 0
            if diff > Decimal("100") and pct > Decimal("5"):
                add("po_invoice_mismatch", [page_num], [doc_id, po_ref],
                    f"PO {po_ref} amount {po_data[po_ref]['amount']} ≠ invoice {inv_total}",
                    str(inv_total), str(po_data[po_ref]['amount']))


# ===================================================================
# 3. DOUBLE PAYMENT (10 needles, 3pts each)
# Same invoice amount paid twice in bank statement
# ===================================================================
print("\n[C] Double payments...")
bank_credits = defaultdict(list)
for page_num, doc_id, text in bank_pages:
    # Look for transaction amounts
    for m in re.finditer(r'(\d{1,2}/\d{1,2}/\d{4})\s+.*?(\d{1,3}(?:,\d{3})*\.\d{2})\s+(\d{1,3}(?:,\d{3})*\.\d{2})', text):
        amt = clean_num(m.group(2))
        if amt and amt > Decimal("1000"):
            bank_credits[str(amt)].append((page_num, doc_id, m.group(1)))

for amt_str, occurrences in bank_credits.items():
    if len(occurrences) >= 2:
        pages = [o[0] for o in occurrences[:2]]
        doc_ids = list(dict.fromkeys([o[1] for o in occurrences[:2]]))
        add("double_payment", pages, doc_ids,
            f"Amount {amt_str} paid on {occurrences[0][2]} and again on {occurrences[1][2]}",
            f"Paid twice: {amt_str}", "Should be paid once")


# ===================================================================
# 4. DUPLICATE EXPENSE (10 needles, 3pts each)
# Same expense submitted twice across expense reports
# ===================================================================
print("\n[D] Duplicate expenses...")
expense_map = defaultdict(list)
for page_num, doc_id, text in expense_pages:
    for m in re.finditer(r'(\d{1,2}[/-]\d{1,2}[/-]\d{4})\s+([A-Za-z\s]{5,40})\s+([\d,]+\.\d{2})', text):
        key = f"{m.group(2).strip().lower()}_{clean_num(m.group(3))}"
        expense_map[key].append((page_num, doc_id, m.group(1)))

for key, hits in expense_map.items():
    if len(hits) >= 2:
        desc_part, amt_part = key.rsplit("_", 1)
        pages = [h[0] for h in hits[:2]]
        doc_ids = list(dict.fromkeys([h[1] for h in hits[:2]]))
        add("duplicate_expense", pages, doc_ids,
            f"Expense '{desc_part}' for {amt_part} submitted on {hits[0][2]} and {hits[1][2]}",
            f"Duplicate: {amt_part}", "Should appear once")


# ===================================================================
# 5. QUANTITY ACCUMULATION (35 needles, 7pts each)
# Running total of qty for same item exceeds PO qty
# ===================================================================
print("\n[E] Quantity accumulation...")
# Track PO item quantities
po_items = defaultdict(lambda: defaultdict(Decimal))  # po_id -> item -> max_qty
for page_num, doc_id, text in po_pages:
    for line in text.split('\n'):
        m = re.search(r'(\w[\w\s]{3,30})\s+(\d+)\s+(?:Units?|Pcs?|Nos?|Hrs?|Lots?)', line)
        if m:
            item = re.sub(r'\s+', ' ', m.group(1).strip().lower())[:30]
            qty = Decimal(m.group(2))
            po_items[doc_id][item] = max(po_items[doc_id][item], qty)

# Track cumulative invoice quantities
inv_items = defaultdict(lambda: defaultdict(Decimal))  # vendor -> item -> cumulative_qty
inv_item_docs = defaultdict(list)
for page_num, doc_id, text in invoice_pages:
    po_ref_m = re.search(r'PO[- ]?(?:Reference|Ref|No\.?)[:\s]+(PO-\d{4}-\d+)', text)
    if not po_ref_m:
        continue
    po_ref = po_ref_m.group(1)
    for line in text.split('\n'):
        m = re.search(r'(\w[\w\s]{3,30})\s+([\d.]+)\s+(?:Units?|Pcs?|Nos?|Hrs?|Lots?)', line)
        if m:
            item = re.sub(r'\s+', ' ', m.group(1).strip().lower())[:30]
            qty = clean_num(m.group(2))
            if qty:
                inv_items[po_ref][item] += qty
                inv_item_docs[f"{po_ref}_{item}"].append((page_num, doc_id))

for po_ref, items in po_items.items():
    for item, max_qty in items.items():
        cumulative = inv_items[po_ref].get(item, Decimal("0"))
        if cumulative > max_qty * Decimal("1.05"):  # 5% tolerance
            docs = inv_item_docs.get(f"{po_ref}_{item}", [])
            if docs:
                pages = list(dict.fromkeys([d[0] for d in docs]))[:3]
                doc_ids = list(dict.fromkeys([d[1] for d in docs]))[:3]
                add("quantity_accumulation", pages, [po_ref] + doc_ids,
                    f"PO {po_ref} allows {max_qty} of '{item}' but invoices total {cumulative}",
                    str(cumulative), str(max_qty))


# ===================================================================
# 6. TRIPLE EXPENSE CLAIM (10 needles, 7pts each)
# Same expense claimed 3 times (subset of duplicate_expense)
# ===================================================================
print("\n[F] Triple expense claims...")
for key, hits in expense_map.items():
    if len(hits) >= 3:
        desc_part, amt_part = key.rsplit("_", 1)
        pages = [h[0] for h in hits[:3]]
        doc_ids = list(dict.fromkeys([h[1] for h in hits[:3]]))
        add("triple_expense_claim", pages, doc_ids,
            f"Expense '{desc_part}' for {amt_part} submitted 3 times",
            f"Count: {len(hits)}", "Should appear once")


# ===================================================================
# 7. EMPLOYEE ID COLLISION (7 needles, 7pts each)
# Two employees share the same employee ID
# ===================================================================
print("\n[G] Employee ID collisions...")
emp_id_to_names = defaultdict(set)
emp_id_to_docs = defaultdict(list)
for page_num, doc_id, text in expense_pages:
    # Match employee name + ID patterns
    emp_m = re.search(r'Employee[:\s]+([A-Z][A-Za-z\s]+)', text)
    id_m  = re.search(r'(?:Employee\s*)?ID[:\s]+([A-Z]{2,4}\d{4,6})', text)
    if emp_m and id_m:
        name = emp_m.group(1).strip()[:30]
        eid  = id_m.group(1).strip()
        emp_id_to_names[eid].add(name)
        emp_id_to_docs[eid].append((page_num, doc_id))

for eid, names in emp_id_to_names.items():
    if len(names) >= 2:
        docs = emp_id_to_docs[eid]
        pages = [d[0] for d in docs[:2]]
        doc_ids = list(dict.fromkeys([d[1] for d in docs[:2]]))
        add("employee_id_collision", pages, doc_ids,
            f"Employee ID {eid} used by: {' and '.join(list(names)[:2])}",
            f"ID {eid}", "Unique per employee")


# ===================================================================
# 8. BALANCE DRIFT — supplement existing (15 needles, 7pts each)
# Pick up any balance_drift not yet in submission
# ===================================================================
print("\n[H] Additional bank balance drift...")
bank_data = {}
for page_num, doc_id, text in bank_pages:
    open_m  = re.search(r'Opening Balance[:\s]+[■₹]?([\d,]+\.?\d*)', text, re.IGNORECASE)
    close_m = re.search(r'Closing Balance[:\s]+[■₹]?([\d,]+\.?\d*)', text, re.IGNORECASE)
    if open_m and close_m:
        bank_data[doc_id] = {
            "page": page_num,
            "opening": clean_num(open_m.group(1)),
            "closing": clean_num(close_m.group(1))
        }

sorted_banks = sorted(bank_data.items())
for i in range(1, len(sorted_banks)):
    prev_id, prev = sorted_banks[i-1]
    curr_id, curr = sorted_banks[i]
    if prev["closing"] and curr["opening"]:
        if abs(prev["closing"] - curr["opening"]) > Decimal("0.01"):
            add("balance_drift", [curr["page"]], [curr_id],
                f"Statement {curr_id}: opening {curr['opening']} ≠ prev closing {prev['closing']}",
                str(curr["opening"]), str(prev["closing"]))


# ===================================================================
# 9. CIRCULAR REFERENCE (8 needles, 7pts each)
# Expense report references an invoice that references the expense back
# ===================================================================
print("\n[I] Circular references...")
inv_to_expense = {}
expense_to_inv = {}
for page_num, doc_id, text in expense_pages:
    inv_ref_m = re.search(r'INV-\d{4}-\d{5}', text)
    if inv_ref_m:
        expense_to_inv[doc_id] = inv_ref_m.group(0)

for page_num, doc_id, text in invoice_pages:
    exp_ref_m = re.search(r'EXP-\d{4}-\d{5}', text)
    if exp_ref_m:
        inv_to_expense[doc_id] = exp_ref_m.group(0)

for exp_doc, inv_ref in expense_to_inv.items():
    if inv_ref in inv_to_expense and inv_to_expense[inv_ref] == exp_doc:
        # Find pages
        exp_pages = [p for p, d, t in expense_pages if d == exp_doc]
        add("circular_reference",
            exp_pages[:1] if exp_pages else [0],
            [exp_doc, inv_ref],
            f"Expense {exp_doc} references {inv_ref} which references back to {exp_doc}",
            f"{exp_doc}↔{inv_ref}", "No circular references allowed")


# ===================================================================
# 10. VENDOR NAME TYPO — supplement existing with more (10 needles, 3pts)
# ===================================================================
print("\n[J] Additional vendor name typos...")
def edit_distance(s1, s2):
    m, n = len(s1), len(s2)
    dp = list(range(n+1))
    for i in range(1, m+1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n+1):
            temp = dp[j]
            dp[j] = prev if s1[i-1]==s2[j-1] else 1 + min(prev, dp[j], dp[j-1])
            prev = temp
    return dp[n]

for page_num, doc_id, text in invoice_pages:
    vendor_m = re.search(
        r'(?:VENDOR DETAILS|Vendor Name|Name)[:\s\n]+([A-Z][A-Za-z\s&.]+(?:Ltd|Inc|Pvt|Corp|LLP)\.?)',
        text
    )
    if not vendor_m:
        continue
    found = vendor_m.group(1).strip()
    if found in REGISTERED_VENDORS:
        continue
    for master_name in REGISTERED_VENDORS:
        if abs(len(found) - len(master_name)) > 5:
            continue
        dist = edit_distance(found.lower(), master_name.lower())
        if 1 <= dist <= 3:
            add("vendor_name_typo", [page_num], [doc_id],
                f"'{found}' appears to be a typo of '{master_name}' (edit distance {dist})",
                found, master_name)
            break


conn.close()

# ===================================================================
# MERGE with existing submission
# ===================================================================
print(f"\nNew findings detected: {len(new_findings)}")

# Cap high-volume new categories to their max
MAX_PER_CATEGORY = {
    'arithmetic_error': 12, 'billing_typo': 4, 'duplicate_line_item': 4,
    'invalid_date': 10, 'wrong_tax_rate': 10, 'po_invoice_mismatch': 15,
    'vendor_name_typo': 10, 'double_payment': 10, 'ifsc_mismatch': 5,
    'duplicate_expense': 10, 'date_cascade': 5, 'gstin_state_mismatch': 5,
    'quantity_accumulation': 35, 'price_escalation': 10, 'balance_drift': 15,
    'circular_reference': 8, 'triple_expense_claim': 10, 'employee_id_collision': 7,
    'fake_vendor': 10, 'phantom_po_reference': 5,
}

# Count how many of each category exist already
existing_counts = Counter(f["category"] for f in existing)

# Add new findings up to remaining capacity
to_add = []
new_counts = Counter()
for f in new_findings:
    cat = f["category"]
    max_allowed = MAX_PER_CATEGORY.get(cat, 5)
    already_have = existing_counts.get(cat, 0)
    if already_have + new_counts.get(cat, 0) < max_allowed:
        to_add.append(f)
        new_counts[cat] += 1

print(f"Adding {len(to_add)} new findings (capped to maximums)")
for cat, cnt in sorted(new_counts.items()):
    print(f"  +{cnt:3d}  {cat}")

# Merge and re-number
all_findings = existing + to_add
for i, f in enumerate(all_findings):
    f["finding_id"] = f"F-{i+1:03d}"

result = {"team_id": "apex_null", "findings": all_findings}
with open("submission.json", "w") as f:
    json.dump(result, f, indent=2)

# Score estimate
POINTS = {
    'arithmetic_error':1,'billing_typo':1,'duplicate_line_item':1,'invalid_date':1,'wrong_tax_rate':1,
    'po_invoice_mismatch':3,'vendor_name_typo':3,'double_payment':3,'ifsc_mismatch':3,
    'duplicate_expense':3,'date_cascade':3,'gstin_state_mismatch':3,
    'quantity_accumulation':7,'price_escalation':7,'balance_drift':7,'circular_reference':7,
    'triple_expense_claim':7,'employee_id_collision':7,'fake_vendor':7,'phantom_po_reference':7
}
cats = Counter(f["category"] for f in all_findings)
total_pts = sum(cats.get(c, 0) * p for c, p in POINTS.items())

print(f"\n{'='*55}")
print(f"Final submission: {len(all_findings)} findings")
for cat, cnt in sorted(cats.items(), key=lambda x: -POINTS.get(x[0],1)):
    pts = POINTS.get(cat, 1)
    print(f"  {cat:35s} {cnt:3d}  @ {pts}pt  = {cnt*pts}")
print(f"Estimated max score if all correct: {total_pts} pts")
print(f"{'='*55}")
print("Saved → submission.json")

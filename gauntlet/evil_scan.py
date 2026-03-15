"""
evil_scan.py — Targets high-value evil needles worth 7pts each.
Run: python gauntlet/evil_scan.py
"""

import sqlite3
import json
import re
import sys
import os
from decimal import Decimal, ROUND_HALF_UP
from collections import defaultdict
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from gauntlet.vendor_master import VENDOR_MASTER

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("gauntlet.db")
findings = []
fid = 1


def add(category, pages, doc_refs, description, reported, correct):
    global fid
    findings.append({
        "finding_id": f"E-{fid:03d}",
        "category": category,
        "pages": pages if isinstance(pages, list) else [pages],
        "document_refs": doc_refs if isinstance(doc_refs, list) else [doc_refs],
        "description": description,
        "reported_value": str(reported),
        "correct_value": str(correct)
    })
    fid += 1
    print(f"  [E-{fid-1:03d}] {category} | {doc_refs} | {reported} -> {correct}")


def clean(s):
    """Clean a string to a Decimal number, removing currency symbols, commas, spaces."""
    if s is None:
        return None
    s = re.sub(r'[^\d.\-]', '', str(s))
    try:
        return Decimal(s)
    except Exception:
        return None


def fmt_num(n):
    """Format number with commas."""
    try:
        d = Decimal(str(n))
        return f"{d:,}"
    except Exception:
        return str(n)


# Load all pages once
all_pages = conn.execute(
    "SELECT page_num, doc_id, doc_type, raw_text FROM pages WHERE page_num > 4"
).fetchall()

invoice_pages = [(p, d, t) for p, d, dt, t in all_pages if dt == 'invoice' and d]
bank_pages    = [(p, d, t) for p, d, dt, t in all_pages if dt == 'bank_statement' and d]
expense_pages = [(p, d, t) for p, d, dt, t in all_pages if dt == 'expense_report' and d]
po_pages      = [(p, d, t) for p, d, dt, t in all_pages if dt == 'purchase_order' and d]

print(f"Loaded: {len(invoice_pages)} invoices, {len(bank_pages)} bank stmts, "
      f"{len(expense_pages)} expenses, {len(po_pages)} POs")

# ============================================================
# EVIL 1: QUANTITY ACCUMULATION
# Sum of all invoice quantities against a PO exceeds PO qty
# Worth 7pts each, max 35
# ============================================================
print("\n[EVIL-1] Quantity accumulation...")

# Build PO line items from newline-separated format:
# Description\nHSN\nQty\nUnit\n■Rate\n■Amount
po_quantities = defaultdict(dict)
po_doc_pages = {}

for page_num, doc_id, text in po_pages:
    po_doc_pages[doc_id] = page_num
    lines = text.split('\n')
    for i, line in enumerate(lines):
        # Look for qty line: a plain number followed by a unit line
        qty_m = re.match(r'^(\d+(?:\.\d+)?)$', line.strip())
        if qty_m and i + 1 < len(lines) and i >= 2:
            unit_line = lines[i + 1].strip() if i + 1 < len(lines) else ''
            if unit_line in ('Hrs', 'Units', 'Pcs', 'Nos', 'Days', 'Months', 'Lots', 'Kgs', 'Ltrs', 'Boxes', 'Sets'):
                qty = Decimal(qty_m.group(1))
                # Description is 2 lines back (after HSN)
                desc = lines[i - 2].strip() if i >= 2 else 'Unknown'
                hsn_m = re.match(r'^(\d{6,8})$', lines[i - 1].strip())
                if hsn_m:
                    desc = lines[i - 2].strip()[:40]
                else:
                    desc = lines[i - 1].strip()[:40]

                # Rate is next-next line (after unit), starts with ■
                if i + 2 < len(lines):
                    rate_m = re.match(r'^[^\d]*([\d,]+\.?\d*)$', lines[i + 2].strip())
                    rate = clean(rate_m.group(1)) if rate_m else None
                else:
                    rate = None

                if qty > 0:
                    po_quantities[doc_id][desc] = {
                        "allowed_qty": qty,
                        "rate": rate,
                        "page": page_num
                    }

# Build invoice quantities against each PO
invoice_quantities = defaultdict(lambda: defaultdict(list))
invoice_by_po = defaultdict(list)

for page_num, doc_id, text in invoice_pages:
    po_m = re.search(r'PO Reference:\n(PO-\d{4}-\d+)', text)
    if not po_m:
        continue
    po_ref = po_m.group(1)
    invoice_by_po[po_ref].append((page_num, doc_id))

    lines = text.split('\n')
    for i, line in enumerate(lines):
        qty_m = re.match(r'^(\d+(?:\.\d+)?)$', line.strip())
        if qty_m and i + 1 < len(lines):
            unit_line = lines[i + 1].strip()
            if unit_line in ('Hrs', 'Units', 'Pcs', 'Nos', 'Days', 'Months', 'Lots', 'Kgs', 'Ltrs', 'Boxes', 'Sets'):
                qty = Decimal(qty_m.group(1))
                # Get description
                desc = lines[i - 2].strip()[:40] if i >= 2 else 'Unknown'
                if qty > 0:
                    invoice_quantities[po_ref][desc].append({
                        "qty": qty,
                        "doc_id": doc_id,
                        "page": page_num
                    })

# Compare totals
qty_accum_count = 0
for po_id, po_lines in po_quantities.items():
    if po_id not in invoice_by_po:
        continue
    for desc, po_info in po_lines.items():
        allowed = po_info["allowed_qty"]
        # Find matching invoice lines by fuzzy description match
        inv_items = None
        for inv_desc, inv_list in invoice_quantities[po_id].items():
            if (desc[:15].lower() in inv_desc.lower() or
                inv_desc[:15].lower() in desc.lower()):
                inv_items = inv_list
                break
        if not inv_items:
            continue

        total_invoiced = sum(i["qty"] for i in inv_items)
        # Flag if total exceeds PO by more than 10%
        if total_invoiced > allowed * Decimal("1.10") and len(inv_items) >= 2:
            all_inv_docs = list({i["doc_id"] for i in inv_items})
            all_inv_pages = list({i["page"] for i in inv_items})
            doc_refs = [po_id] + all_inv_docs[:4]
            pages = [po_doc_pages.get(po_id, 0)] + all_inv_pages[:3]
            add("quantity_accumulation",
                [p for p in pages if p > 0], doc_refs,
                f"PO allows {allowed} units of '{desc[:25]}' but {total_invoiced} invoiced across {len(all_inv_docs)} invoices",
                fmt_num(total_invoiced),
                fmt_num(allowed))
            qty_accum_count += 1

print(f"  Found: {qty_accum_count}")

# ============================================================
# EVIL 2: PRICE ESCALATION
# Invoice charges rate exceeding PO contracted rate
# Worth 7pts each, max 10
# ============================================================
print("\n[EVIL-2] Price escalation...")

price_esc_count = 0
for po_id, po_lines in po_quantities.items():
    if po_id not in invoice_by_po:
        continue
    for desc, po_info in po_lines.items():
        contracted_rate = po_info.get("rate")
        if not contracted_rate or contracted_rate == 0:
            continue

        # Find all invoice rates for items matching this PO line
        for page_num, doc_id, text in invoice_pages:
            po_m = re.search(r'PO Reference:\n(PO-\d{4}-\d+)', text)
            if not po_m or po_m.group(1) != po_id:
                continue

            lines = text.split('\n')
            for i, line in enumerate(lines):
                # Check if this line is a rate (■-prefixed)
                rate_m = re.match(r'^[^\d]*([\d,]+\.\d{2})$', line.strip())
                if rate_m and i + 1 < len(lines):
                    # Next line should be amount (also ■-prefixed)
                    amt_m = re.match(r'^[^\d]*([\d,]+\.\d{2})$', lines[i + 1].strip())
                    if amt_m and i >= 2:
                        # line i-2 should be unit, i-3 should be qty
                        unit_line = lines[i - 1].strip() if i >= 1 else ''
                        if unit_line in ('Hrs', 'Units', 'Pcs', 'Nos', 'Days', 'Months', 'Lots', 'Kgs', 'Ltrs', 'Boxes', 'Sets'):
                            inv_rate = clean(rate_m.group(1))
                            if inv_rate and inv_rate > contracted_rate * Decimal("1.05"):
                                # Verify description matches
                                desc_line = lines[i - 4].strip()[:40] if i >= 4 else ''
                                if desc[:10].lower() in desc_line.lower() or desc_line[:10].lower() in desc.lower():
                                    add("price_escalation",
                                        [po_doc_pages.get(po_id, 0), page_num],
                                        [po_id, doc_id],
                                        f"PO rate {contracted_rate} for '{desc[:25]}' but invoice charges {inv_rate}",
                                        fmt_num(inv_rate),
                                        fmt_num(contracted_rate))
                                    price_esc_count += 1

print(f"  Found: {price_esc_count}")

# ============================================================
# EVIL 3: BALANCE DRIFT
# Bank statement opening != previous month closing
# Worth 7pts each, max 15
# ============================================================
print("\n[EVIL-3] Balance drift...")

bank_data = {}
for page_num, doc_id, text in bank_pages:
    open_m = re.search(r'Opening Balance:\n[^\d]*([\d,]+\.\d{2})', text)
    close_m = re.search(r'Closing Balance:\n[^\d]*([\d,]+\.\d{2})', text)
    period_m = re.search(r'Period:\n(\d{2}/\d{2}/\d{4})\s+to\s+(\d{2}/\d{2}/\d{4})', text)

    if open_m and period_m:
        try:
            period_start = datetime.strptime(period_m.group(1), '%d/%m/%Y')
            bank_data[doc_id] = {
                "page": page_num,
                "opening": clean(open_m.group(1)),
                "closing": clean(close_m.group(1)) if close_m else None,
                "period_start": period_start,
                "period_str": period_m.group(1),
                "account": re.search(r'Account\s*(?:No|Number)[:\s]+(\d+)', text).group(1) if re.search(r'Account\s*(?:No|Number)[:\s]+(\d+)', text) else "unknown"
            }
        except Exception:
            pass

# Group by account and sort by period
accounts = defaultdict(list)
for doc_id, data in bank_data.items():
    accounts[data["account"]].append((doc_id, data))

drift_count = 0
for account, entries in accounts.items():
    sorted_entries = sorted(entries, key=lambda x: x[1]["period_start"])
    for i in range(1, len(sorted_entries)):
        prev_id, prev = sorted_entries[i - 1]
        curr_id, curr = sorted_entries[i]
        if prev["closing"] and curr["opening"]:
            diff = abs(prev["closing"] - curr["opening"])
            if diff > Decimal("1.00"):
                add("balance_drift",
                    [prev["page"], curr["page"]],
                    [prev_id, curr_id],
                    f"Opening {curr['opening']} != prev closing {prev['closing']} (diff={fmt_num(diff)})",
                    str(curr["opening"]),
                    str(prev["closing"]))
                drift_count += 1

# Also check without account grouping (all bank stmts sorted by date)
if drift_count == 0:
    sorted_all = sorted(bank_data.items(), key=lambda x: x[1]["period_start"])
    for i in range(1, len(sorted_all)):
        prev_id, prev = sorted_all[i - 1]
        curr_id, curr = sorted_all[i]
        if prev["closing"] and curr["opening"]:
            diff = abs(prev["closing"] - curr["opening"])
            if diff > Decimal("1.00"):
                add("balance_drift",
                    [prev["page"], curr["page"]],
                    [prev_id, curr_id],
                    f"Opening {curr['opening']} != prev closing {prev['closing']} (diff={fmt_num(diff)})",
                    str(curr["opening"]),
                    str(prev["closing"]))
                drift_count += 1

print(f"  Found: {drift_count}")

# ============================================================
# EVIL 4: TRIPLE EXPENSE CLAIM
# Same expense in 3+ different reports
# Worth 7pts each, max 10
# ============================================================
print("\n[EVIL-4] Triple expense claims...")

expense_index = defaultdict(list)
for page_num, doc_id, text in expense_pages:
    lines = text.split('\n')
    for i, line in enumerate(lines):
        # Look for date patterns in expense lines
        m = re.search(
            r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})',
            line
        )
        if m:
            date = m.group(1).strip()
            # Look for amount on same or nearby lines
            amt_m = re.search(r'[^\d]*([\d,]+\.\d{2})', line)
            if not amt_m:
                # Check next few lines
                for j in range(1, 4):
                    if i + j < len(lines):
                        amt_m = re.search(r'[^\d]*([\d,]+\.\d{2})', lines[i + j])
                        if amt_m:
                            break

            if amt_m:
                amount = clean(amt_m.group(1))
                if amount and amount > Decimal('100'):
                    # Get description from nearby text
                    desc_text = line[:50].strip()
                    key = f"{date}|{amount}"
                    expense_index[key].append({
                        "doc_id": doc_id,
                        "page": page_num,
                        "amount": amount,
                        "desc": desc_text
                    })

triple_count = 0
for key, occurrences in expense_index.items():
    unique_docs = list({o["doc_id"] for o in occurrences})
    if len(unique_docs) >= 3:
        parts = key.split('|')
        amount = parts[1] if len(parts) > 1 else "0"
        doc_refs = unique_docs[:3]
        pages = [o["page"] for o in occurrences[:3]]
        desc = occurrences[0].get("desc", "expense")
        add("triple_expense_claim",
            pages, doc_refs,
            f"Expense on {parts[0]} for {amount} claimed in {len(unique_docs)} reports",
            f"{len(unique_docs)} x {fmt_num(amount)}",
            f"1 x {fmt_num(amount)}")
        triple_count += 1

print(f"  Found: {triple_count}")

# ============================================================
# EVIL 5: EMPLOYEE ID COLLISION
# Same employee ID used by different people
# Worth 7pts each, max 7
# ============================================================
print("\n[EVIL-5] Employee ID collisions...")

emp_registry = defaultdict(lambda: {"names": set(), "docs": [], "pages": []})
for page_num, doc_id, text in expense_pages:
    emp_id_m = re.search(r'Employee\s*(?:ID|Code)[:\s\n]+([A-Z0-9\-]+)', text, re.IGNORECASE)
    emp_name_m = re.search(r'Employee\s*Name[:\s\n]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', text, re.IGNORECASE)

    if not emp_name_m:
        # Try alternate pattern: Name:\nActual Name
        emp_name_m = re.search(r'Name:\n([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)', text)

    if emp_id_m and emp_name_m:
        emp_id = emp_id_m.group(1).strip()
        emp_name = emp_name_m.group(1).strip()
        emp_registry[emp_id]["names"].add(emp_name)
        emp_registry[emp_id]["docs"].append(doc_id)
        emp_registry[emp_id]["pages"].append(page_num)

collision_count = 0
for emp_id, data in emp_registry.items():
    if len(data["names"]) >= 2:
        names = list(data["names"])
        docs = list(dict.fromkeys(data["docs"]))[:2]
        pages = data["pages"][:2]
        add("employee_id_collision",
            pages, docs,
            f"Employee ID {emp_id} used by: {', '.join(names[:3])}",
            f"{emp_id}: {names[0]}",
            f"{emp_id}: {names[1]}")
        collision_count += 1

print(f"  Found: {collision_count}")

# ============================================================
# EVIL 6: CIRCULAR REFERENCE
# Credit/debit notes reference each other in a loop
# Worth 7pts each, max 8
# ============================================================
print("\n[EVIL-6] Circular references...")

# Build reference graph from all documents
ref_graph = {}
doc_pages = {}
for page_num, doc_id, doc_type, text in all_pages:
    if doc_id:
        doc_pages[doc_id] = page_num
        if doc_type in ('credit_note', 'debit_note'):
            # Find what this note references
            ref_m = re.search(
                r'(?:Against|Reference|Ref|For|Original)[:\s\n]+((?:CN|DN|INV|CR|DR)-\d{4}-\d+)',
                text, re.IGNORECASE
            )
            if ref_m:
                ref_graph[doc_id] = ref_m.group(1)


# Detect cycles
def find_cycle(start, graph, visited=None, path=None):
    if visited is None:
        visited = set()
    if path is None:
        path = []
    if start in visited:
        if start in path:
            cycle_start = path.index(start)
            return path[cycle_start:]
        return None
    visited.add(start)
    path.append(start)
    next_node = graph.get(start)
    if next_node:
        result = find_cycle(next_node, graph, visited, path)
        if result:
            return result
    path.pop()
    return None


reported_cycles = set()
circ_count = 0
for doc_id in ref_graph:
    cycle = find_cycle(doc_id, ref_graph)
    if cycle and len(cycle) >= 2:
        cycle_key = "->".join(sorted(cycle))
        if cycle_key not in reported_cycles:
            reported_cycles.add(cycle_key)
            chain = "->".join(cycle) + "->" + cycle[0]
            doc_refs = cycle[:8]
            pages = [doc_pages.get(d, 0) for d in cycle[:4]]
            add("circular_reference",
                [p for p in pages if p > 0],
                doc_refs,
                f"Circular reference chain: {chain}",
                chain,
                "no circular refs should exist")
            circ_count += 1

print(f"  Found: {circ_count}")

# ============================================================
# EVIL 7: PO-INVOICE TOTAL MISMATCH
# Invoice grand total doesn't match sum of line items
# Worth 3pts each (medium), but adds more findings
# ============================================================
print("\n[EVIL-7] PO-Invoice mismatches (invoiced amount > PO total)...")

# Build PO totals
po_totals = {}
for page_num, doc_id, text in po_pages:
    total_m = re.search(r'(?:GRAND TOTAL|Total)[:\s\n]+[^\d]*([\d,]+\.\d{2})', text)
    if total_m:
        po_totals[doc_id] = {
            "total": clean(total_m.group(1)),
            "page": page_num
        }

# Check invoices against their PO totals
po_inv_mismatch_count = 0
po_invoiced_totals = defaultdict(lambda: {"total": Decimal("0"), "invoices": []})

for page_num, doc_id, text in invoice_pages:
    po_m = re.search(r'PO Reference:\n(PO-\d{4}-\d+)', text)
    if not po_m:
        continue
    po_ref = po_m.group(1)

    # Get invoice grand total
    total_m = re.search(r'GRAND TOTAL[:\s\n]+[^\d]*([\d,]+\.\d{2})', text)
    if total_m:
        inv_total = clean(total_m.group(1))
        if inv_total:
            po_invoiced_totals[po_ref]["total"] += inv_total
            po_invoiced_totals[po_ref]["invoices"].append({
                "doc_id": doc_id,
                "page": page_num,
                "total": inv_total
            })

for po_ref, inv_data in po_invoiced_totals.items():
    if po_ref in po_totals:
        po_total = po_totals[po_ref]["total"]
        invoiced = inv_data["total"]
        if po_total and invoiced > po_total * Decimal("1.10"):
            all_refs = [po_ref] + [i["doc_id"] for i in inv_data["invoices"][:3]]
            all_pages_list = [po_totals[po_ref]["page"]] + [i["page"] for i in inv_data["invoices"][:3]]
            add("po_invoice_mismatch",
                all_pages_list, all_refs,
                f"Total invoiced {fmt_num(invoiced)} exceeds PO total {fmt_num(po_total)} by {fmt_num(invoiced - po_total)}",
                fmt_num(invoiced),
                fmt_num(po_total))
            po_inv_mismatch_count += 1

print(f"  Found: {po_inv_mismatch_count}")

# ============================================================
# EVIL 8: DUPLICATE EXPENSE
# Same expense in 2 different reports
# Worth 3pts each (medium)
# ============================================================
print("\n[EVIL-8] Duplicate expenses (in 2 reports)...")

dup_exp_count = 0
for key, occurrences in expense_index.items():
    unique_docs = list({o["doc_id"] for o in occurrences})
    if len(unique_docs) == 2:
        parts = key.split('|')
        amount = parts[1] if len(parts) > 1 else "0"
        doc_refs = unique_docs[:2]
        pages = [o["page"] for o in occurrences[:2]]
        add("duplicate_expense",
            pages, doc_refs,
            f"Expense on {parts[0]} for {amount} claimed in 2 reports",
            f"2 x {fmt_num(amount)}",
            f"1 x {fmt_num(amount)}")
        dup_exp_count += 1

print(f"  Found: {dup_exp_count}")

# ============================================================
# EVIL 9: DOUBLE PAYMENT
# Same invoice paid twice in bank statements
# Worth 3pts each (medium)
# ============================================================
print("\n[EVIL-9] Double payments...")

payment_index = defaultdict(list)
for page_num, doc_id, text in bank_pages:
    # Look for invoice references in bank transaction descriptions
    inv_refs = re.findall(r'(INV-\d{4}-\d+)', text)
    for inv_ref in inv_refs:
        payment_index[inv_ref].append({
            "bank_doc": doc_id,
            "page": page_num
        })

double_pay_count = 0
for inv_ref, payments in payment_index.items():
    if len(payments) >= 2:
        docs = [inv_ref] + [p["bank_doc"] for p in payments[:2]]
        pages = [p["page"] for p in payments[:2]]
        add("double_payment",
            pages, docs,
            f"Invoice {inv_ref} paid {len(payments)} times in bank statements",
            f"{len(payments)} payments",
            "1 payment")
        double_pay_count += 1

print(f"  Found: {double_pay_count}")

conn.close()

# ============================================================
# MERGE WITH EXISTING + SAVE
# ============================================================
print(f"\n{'='*60}")
print(f"New evil findings: {len(findings)}")

try:
    with open('submission.json') as f:
        existing_data = json.load(f)
    existing = existing_data.get('findings', [])
except Exception:
    existing = []

print(f"Existing findings: {len(existing)}")

# Deduplicate: skip new finding if same category+doc_ref already in existing
existing_keys = set()
for f_item in existing:
    for ref in f_item.get('document_refs', []):
        existing_keys.add(f"{f_item['category']}_{ref}")

new_unique = []
for f_item in findings:
    key = f"{f_item['category']}_{f_item.get('document_refs', [''])[0]}"
    if key not in existing_keys:
        new_unique.append(f_item)
        existing_keys.add(key)

print(f"New unique evil findings: {len(new_unique)}")

all_findings = existing + new_unique

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

by_cat = defaultdict(list)
for f_item in all_findings:
    by_cat[f_item['category']].append(f_item)

trimmed = []
for cat, items in sorted(by_cat.items()):
    cap = MAX_PER_CATEGORY.get(cat, 5)
    trimmed.extend(items[:cap])

for i, f_item in enumerate(trimmed):
    f_item['finding_id'] = f"F-{i+1:03d}"

result = {"team_id": "apex_null", "findings": trimmed}
with open('submission.json', 'w') as f:
    json.dump(result, f, indent=2)

# Score estimate
from collections import Counter
cats = Counter(f_item['category'] for f_item in trimmed)

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

easy_cats = ['arithmetic_error', 'billing_typo', 'duplicate_line_item', 'invalid_date', 'wrong_tax_rate']
medium_cats = ['po_invoice_mismatch', 'vendor_name_typo', 'double_payment', 'ifsc_mismatch',
               'duplicate_expense', 'date_cascade', 'gstin_state_mismatch']
evil_cats = ['quantity_accumulation', 'price_escalation', 'balance_drift', 'circular_reference',
             'triple_expense_claim', 'employee_id_collision', 'fake_vendor', 'phantom_po_reference']

e = sum(cats.get(c, 0) * 1 for c in easy_cats)
m = sum(cats.get(c, 0) * 3 for c in medium_cats)
ev = sum(cats.get(c, 0) * 7 for c in evil_cats)

print(f"\n{'='*60}")
print(f"FINAL SUBMISSION: {len(trimmed)} findings")
print(f"{'='*60}")
for cat, count in sorted(cats.items(), key=lambda x: -WEIGHTS.get(x[0], 1) * x[1]):
    weight = WEIGHTS.get(cat, 1)
    print(f"  {cat:35s} {count:3d}  ({weight}pt x {count} = {count*weight} pts)")

print(f"\n  Easy:   {e} pts")
print(f"  Medium: {m} pts")
print(f"  Evil:   {ev} pts")
print(f"  TOTAL:  {e+m+ev} pts max")
print(f"{'='*60}")
print(f"\nSubmit submission.json now!")

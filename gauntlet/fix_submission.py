"""
Fix submission.json:
1. Remove bad vendor_name_typo findings (similarity-based false positives)
2. Keep only the real edit-distance typos found by deep_scan
3. For fake_vendor, keep max 10 with diverse company names
4. Verify final counts and score
"""
import json
import sys
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding='utf-8')

with open('submission.json') as f:
    data = json.load(f)

findings = data['findings']
print(f"Starting: {len(findings)} findings")

# The bad vendor_name_typo findings from the old detect_errors.py used similarity_score
# which matched things like "Hindustan Unilever" -> "Cummins India" (wrong!)
# The real typos from deep_scan are edit-distance 1-3 actual character changes:
# - "Zensar Technlogies Ltd" -> "Zensar Technologies Ltd" (1 char)
# - "Tech Mahinrda Ltd" -> "Tech Mahindra Ltd" (1 char)
# - "Larsen & Tourbo Ltd" -> "Larsen & Toubro Ltd" (1 char)
# etc.

# Known bad vendor_name_typo reported_values (from old similarity-based detection)
BAD_VENDOR_TYPOS = {
    "KPIT Technologies Ltd",       # not a typo of Zensar
    "Hindustan Unilever Ltd",      # not a typo of Cummins India
    "Happiest Minds Technologies Ltd",  # not a typo of Zensar
    "Godrej Consumer Products Ltd",    # not a typo of Zensar
}

# Filter out bad vendor_name_typo findings
cleaned = []
removed = 0
for f in findings:
    if f['category'] == 'vendor_name_typo' and f.get('reported_value') in BAD_VENDOR_TYPOS:
        removed += 1
        print(f"  REMOVED bad typo: {f['reported_value']} -> {f['correct_value']}")
    else:
        cleaned.append(f)

print(f"\nRemoved {removed} bad vendor_name_typo findings")
print(f"Remaining: {len(cleaned)} findings")

# Check category counts
by_cat = defaultdict(list)
for f in cleaned:
    by_cat[f['category']].append(f)

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

# For fake_vendor: keep diverse company names (not all same company repeated)
# Prefer: unique company names, then fill with others
if 'fake_vendor' in by_cat:
    fv = by_cat['fake_vendor']
    # Group by reported_value (company name)
    by_company = defaultdict(list)
    for f in fv:
        by_company[f['reported_value']].append(f)
    
    # Pick one per company, up to max 10
    diverse = []
    for company, items in sorted(by_company.items()):
        diverse.append(items[0])  # first occurrence
    
    # Sort by doc_id for consistency
    diverse.sort(key=lambda x: x.get('document_refs', [''])[0])
    by_cat['fake_vendor'] = diverse[:MAX_PER_CATEGORY['fake_vendor']]
    print(f"\nFake vendor companies kept: {[f['reported_value'] for f in by_cat['fake_vendor']]}")

# Trim all categories to max
trimmed = []
for cat in sorted(by_cat.keys()):
    items = by_cat[cat]
    max_allowed = MAX_PER_CATEGORY.get(cat, 5)
    trimmed.extend(items[:max_allowed])

# Renumber
for i, f in enumerate(trimmed):
    f['finding_id'] = f"F-{i+1:03d}"

result = {"team_id": "apex_null", "findings": trimmed}
with open('submission.json', 'w') as f:
    json.dump(result, f, indent=2)

# Score estimate
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

cats = Counter(f['category'] for f in trimmed)
print(f"\n{'='*60}")
print(f"FINAL SUBMISSION: {len(trimmed)} findings")
print(f"{'='*60}")
total = 0
for cat in sorted(cats.keys()):
    count = cats[cat]
    pts = WEIGHTS.get(cat, 1)
    cat_pts = count * pts
    total += cat_pts
    print(f"  {cat:35s} {count:3d}  ({pts}pt x {count} = {cat_pts}pts)")
print(f"\n  ESTIMATED MAX SCORE: {total} pts")
print(f"{'='*60}")
print("Saved -> submission.json")

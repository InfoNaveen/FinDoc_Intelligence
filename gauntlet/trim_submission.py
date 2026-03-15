import json
from collections import Counter

with open('submission.json') as f:
    data = json.load(f)

findings = data['findings']

# Maximum allowed per category based on hackathon needle counts
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

# CONFIDENCE SCORING — rank findings before trimming
# Higher reported/correct value difference = more likely real
def confidence_score(f):
    score = 0
    # Prefer findings with actual values
    if f.get('reported_value') and f.get('reported_value') != '':
        score += 2
    if f.get('correct_value') and f.get('correct_value') != '':
        score += 2
    # Prefer findings with specific document refs
    if f.get('document_refs') and f['document_refs'] != ['UNKNOWN']:
        score += 3
    # Prefer findings with specific pages
    if f.get('pages') and f['pages'] != [0]:
        score += 2
    # Prefer findings where reported != correct (real discrepancy)
    if f.get('reported_value') != f.get('correct_value'):
        score += 3
    return score

# Group by category
from collections import defaultdict
by_category = defaultdict(list)
for f in findings:
    by_category[f['category']].append(f)

# Trim each category to max, keeping highest confidence
trimmed = []
dropped = 0
for category, items in by_category.items():
    max_allowed = MAX_PER_CATEGORY.get(category, 5)
    # Sort by confidence descending
    ranked = sorted(items, key=confidence_score, reverse=True)
    kept = ranked[:max_allowed]
    trimmed.extend(kept)
    drop_count = len(items) - len(kept)
    dropped += drop_count
    print(f"  {category:35s} {len(items):4d} → {len(kept):3d}  (dropped {drop_count})")

# Renumber finding IDs
for i, f in enumerate(trimmed):
    f['finding_id'] = f"F-{i+1:03d}"

result = {
    "team_id": "apex_null",
    "findings": trimmed
}

with open('submission.json', 'w') as f:
    json.dump(result, f, indent=2)

print(f"\n{'='*55}")
print(f"Before: {len(findings)} findings")
print(f"After:  {len(trimmed)} findings")
print(f"Dropped: {dropped} likely false positives")
print(f"Saved → submission.json")

# Expected score estimate
cats = Counter(f['category'] for f in trimmed)
easy = ['arithmetic_error','billing_typo','duplicate_line_item','invalid_date','wrong_tax_rate']
medium = ['po_invoice_mismatch','vendor_name_typo','double_payment','ifsc_mismatch','duplicate_expense','date_cascade','gstin_state_mismatch']
evil = ['quantity_accumulation','price_escalation','balance_drift','circular_reference','triple_expense_claim','employee_id_collision','fake_vendor','phantom_po_reference']

easy_pts = sum(cats.get(c,0) * 1 for c in easy)
medium_pts = sum(cats.get(c,0) * 3 for c in medium)
evil_pts = sum(cats.get(c,0) * 7 for c in evil)
total_pts = easy_pts + medium_pts + evil_pts

print(f"\nEstimated max score if all correct:")
print(f"  Easy:   {easy_pts} pts")
print(f"  Medium: {medium_pts} pts")
print(f"  Evil:   {evil_pts} pts")
print(f"  Total:  {total_pts} pts")
print(f"{'='*55}")

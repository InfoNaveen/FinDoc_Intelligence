"""Fix wrong_tax_rate values by computing rates from the DB."""
import sqlite3, json, re, sys
from decimal import Decimal

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('gauntlet.db')

with open('submission.json') as f:
    data = json.load(f)

# Build a lookup: doc_id -> (wrong_rate%, correct_rate%)
rate_lookup = {}
rows = conn.execute(
    "SELECT page_num, doc_id, raw_text FROM pages WHERE doc_type='invoice' AND raw_text LIKE '%Subtotal%' AND raw_text LIKE '%CGST%'"
).fetchall()

for page_num, doc_id, text in rows:
    m = re.search(
        r'[■\u25a0]([\d,]+\.\d{2})\nSubtotal:\n[■\u25a0]([\d,]+\.\d{2})\nCGST:\n[■\u25a0]([\d,]+\.\d{2})\nSGST:\n[■\u25a0]([\d,]+\.\d{2})',
        text)
    if not m: continue
    subtotal_str = m.group(2).replace(',', '')
    cgst_str     = m.group(3).replace(',', '')
    sgst_str     = m.group(4).replace(',', '')
    try:
        subtotal = Decimal(subtotal_str)
        cgst     = Decimal(cgst_str)
        sgst     = Decimal(sgst_str)
        if subtotal > 0 and abs(cgst - sgst) > Decimal('1.00'):
            # CGST = subtotal (100%) is wrong; correct CGST/SGST should each be 9% of subtotal
            # The SGST field contains the grand total — it's a label swap error
            # Report: SGST shows grand-total value; correct: SGST should equal CGST
            # Express as: wrong rate implied by SGST vs correct rate (same as CGST rate)
            cgst_rate    = (cgst / subtotal * 100).quantize(Decimal('0.01'))
            # Correct rate for intra-state 18% GST = 9% each
            correct_rate = Decimal('9.00')
            rate_lookup[doc_id] = (str(cgst_rate), str(correct_rate))
    except Exception:
        pass

conn.close()

fixed = 0
for f in data['findings']:
    if f['category'] == 'wrong_tax_rate':
        doc_id = f.get('document_refs', [''])[0]
        if doc_id in rate_lookup:
            wrong_rate, correct_rate = rate_lookup[doc_id]
            f['reported_value'] = f"{wrong_rate}%"
            f['correct_value']  = f"{correct_rate}%"
            fixed += 1
        else:
            # Fallback: parse from current SGST= format
            rep = f.get('reported_value', '')
            cor = f.get('correct_value', '')
            if rep.startswith('SGST='):
                f['reported_value'] = rep  # leave as-is, can't compute without subtotal
            print(f"  WARNING: no rate data for {doc_id}")

print(f"Fixed {fixed} wrong_tax_rate values")

# Show samples
for f in data['findings']:
    if f['category'] == 'wrong_tax_rate':
        print(f"  {f['document_refs']} | reported={f['reported_value']} | correct={f['correct_value']}")
        break

with open('submission.json', 'w') as f:
    json.dump(data, f, indent=2)

print(f"\nSaved -> submission.json")

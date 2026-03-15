import json, re
from decimal import Decimal

with open('submission.json') as f:
    data = json.load(f)

def fmt(n):
    try:
        d = Decimal(str(n).replace(',',''))
        return f"{d:,}"
    except:
        return str(n)

fixed = []
for f in data['findings']:
    cat = f['category']
    r   = f.get('reported_value','')
    c   = f.get('correct_value','')

    if cat == 'fake_vendor':
        c = 'not in vendor master'

    elif cat == 'phantom_po_reference':
        c = 'PO does not exist'

    elif cat == 'balance_drift':
        # Extract number from reported
        num = re.search(r'[\d,]+\.?\d*', r)
        if num:
            r = f"off by {fmt(num.group())}"
        c = 'opening should equal previous closing'

    elif cat == 'circular_reference':
        c = 'no circular refs should exist'

    elif cat == 'duplicate_expense':
        num = re.search(r'[\d,]+\.?\d*', r)
        amt = fmt(num.group()) if num else r
        r = f"2 x {amt}"
        c = f"1 x {amt}"

    elif cat == 'double_payment':
        num = re.search(r'[\d,]+\.?\d*', r)
        amt = fmt(num.group()) if num else r
        r = f"2 payments of {amt}"
        c = f"1 payment of {amt}"

    elif cat == 'triple_expense_claim':
        num = re.search(r'[\d,]+\.?\d*', r)
        amt = fmt(num.group()) if num else r
        r = f"3 x {amt}"
        c = f"1 x {amt}"

    elif cat == 'billing_typo':
        num_r = re.search(r'[\d.]+', r)
        num_c = re.search(r'[\d.]+', c)
        r = f"{num_r.group()} hrs" if num_r else r
        c = f"{num_c.group()} hrs" if num_c else c

    elif cat == 'wrong_tax_rate':
        num_r = re.search(r'[\d.]+', r)
        num_c = re.search(r'[\d.]+', c)
        r = f"{num_r.group()}%" if num_r else r
        c = f"{num_c.group()}%" if num_c else c

    elif cat == 'invalid_date':
        # correct_value must be nearest valid date not text
        import calendar
        m = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', r)
        if m:
            day,month,year = int(m.group(1)),int(m.group(2)),int(m.group(3))
            try:
                max_day = calendar.monthrange(year,month)[1]
                correct_day = min(day, max_day)
                c = f"{correct_day:02d}/{month:02d}/{year}"
            except:
                pass

    elif cat == 'gstin_state_mismatch':
        # Format: reported = "GSTIN starts with XX (StateA)"
        # correct = "Should match address state StateB (code YY)"
        STATE_CODES = {
            "07":"Delhi","27":"Maharashtra","29":"Karnataka",
            "33":"Tamil Nadu","36":"Telangana","24":"Gujarat",
            "19":"West Bengal","09":"Uttar Pradesh","08":"Rajasthan",
        }
        code_m = re.search(r'(\d{2})', r)
        if code_m:
            code = code_m.group(1)
            state = STATE_CODES.get(code, code)
            # Extract address state from description
            desc = f.get('description','')
            addr_m = re.search(r'address\s+(?:shows|says)\s+([A-Za-z\s]+)', desc, re.I)
            addr_state = addr_m.group(1).strip() if addr_m else "Unknown"
            r = f"GSTIN starts with {code} ({state})"
            c = f"Should match address state {addr_state} (code {code})"

    elif cat == 'employee_id_collision':
        # Format: "EMP-XXXX: Name A" and "EMP-XXXX: Name B"
        emp_m = re.search(r'(EMP-[A-Z0-9]+|EMP\d+)', r, re.I)
        if emp_m:
            emp_id = emp_m.group(1)
            if ':' not in r:
                name_m = re.search(r'([A-Z][a-z]+\s+[A-Z][a-z]+)', r)
                if name_m:
                    r = f"{emp_id}: {name_m.group(1)}"
            if ':' not in c:
                name_m = re.search(r'([A-Z][a-z]+\s+[A-Z][a-z]+)', c)
                if name_m:
                    c = f"{emp_id}: {name_m.group(1)}"

    elif cat == 'date_cascade':
        # reported = invoice date, correct = "should be after PO date"
        date_m = re.search(r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})', r)
        if date_m:
            r = date_m.group(1)
        po_date_m = re.search(r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})', c)
        if po_date_m:
            c = f"should be after {po_date_m.group(1)}"

    elif cat in ['arithmetic_error','duplicate_line_item',
                 'quantity_accumulation','price_escalation']:
        # Numbers with commas
        num_r = re.search(r'[\d,]+\.?\d*', r)
        num_c = re.search(r'[\d,]+\.?\d*', c)
        if num_r: r = fmt(num_r.group().replace(',',''))
        if num_c: c = fmt(num_c.group().replace(',',''))
        f['reported_value'] = r
        f['correct_value'] = c

    f['reported_value'] = r
    f['correct_value']  = c
    fixed.append(f)

result = {"team_id": "apex_null", "findings": fixed}
with open('submission.json','w') as f:
    json.dump(result, f, indent=2)

from collections import Counter
cats = Counter(f['category'] for f in fixed)
print(f"Fixed {len(fixed)} findings")
for cat,cnt in sorted(cats.items()):
    print(f"  {cat}: {cnt}")
print("\nsubmission.json ready — SUBMIT NOW")

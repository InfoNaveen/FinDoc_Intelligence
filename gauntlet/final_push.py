# gauntlet/final_push.py
import sqlite3, json, re
from decimal import Decimal
from collections import defaultdict

conn = sqlite3.connect("gauntlet.db")

def clean(s):
    if not s: return None
    try: return Decimal(re.sub(r'[■₹,\s]','',str(s)))
    except: return None

all_p = conn.execute("SELECT page_num,doc_id,doc_type,raw_text FROM pages WHERE page_num>4").fetchall()
inv  = [(p,d,t) for p,d,dt,t in all_p if dt=='invoice' and d]
bank = [(p,d,t) for p,d,dt,t in all_p if dt=='bank_statement' and d]
exp  = [(p,d,t) for p,d,dt,t in all_p if dt=='expense_report' and d]
po   = [(p,d,t) for p,d,dt,t in all_p if dt=='purchase_order' and d]

findings = []
fid = 1

def add(cat,pages,refs,desc,reported,correct):
    global fid
    findings.append({
        "finding_id": f"N-{fid:03d}",
        "category": cat,
        "pages": pages if isinstance(pages,list) else [pages],
        "document_refs": refs if isinstance(refs,list) else [refs],
        "description": desc,
        "reported_value": str(reported),
        "correct_value": str(correct)
    })
    fid += 1
    # print(f"  [{cat}] {refs} | {reported} → {correct}")

# ── BALANCE DRIFT ──────────────────────────────────────────────────────────────
print("\n[BALANCE DRIFT] worth 7pts each, max 15...")
MONTH_ORD = {'january':1,'february':2,'march':3,'april':4,'may':5,'june':6,
             'july':7,'august':8,'september':9,'october':10,'november':11,'december':12}

banks = {}
for pg,did,txt in bank:
    o = re.search(r'Opening\s*Balance[:\s]+[■₹]?([\d,]+\.?\d*)',txt,re.I)
    c = re.search(r'Closing\s*Balance[:\s]+[■₹]?([\d,]+\.?\d*)',txt,re.I)
    m = re.search(r'(?:for|month|period)[:\s]+([A-Za-z]+\s+\d{4})',txt,re.I)
    if o and c:
        mo = m.group(1).strip() if m else ""
        sk = pg
        for mn,n in MONTH_ORD.items():
            if mn in mo.lower():
                yr = re.search(r'(\d{4})',mo)
                sk = (int(yr.group(1)) if yr else 2025)*100+n
                break
        banks[did] = {"pg":pg,"op":clean(o.group(1)),"cl":clean(c.group(1)),"mo":mo,"sk":sk}

for i,(pid,prev) in enumerate(sorted(banks.items(),key=lambda x:x[1]["sk"])):
    for cid,curr in sorted(banks.items(),key=lambda x:x[1]["sk"]):
        if curr["sk"] != prev["sk"]+1: continue
        if prev["cl"] and curr["op"]:
            diff = abs(prev["cl"]-curr["op"])
            if diff > Decimal("1.00"):
                add("balance_drift",
                    [prev["pg"],curr["pg"]],[pid,cid],
                    f"{curr['mo']} opening {curr['op']} != {prev['mo']} closing {prev['cl']}",
                    f"off by {diff:,.2f}",
                    "opening should equal previous closing")

# ── DOUBLE PAYMENT ─────────────────────────────────────────────────────────────
print("[DOUBLE PAYMENT] worth 3pts each, max 10...")
payments = defaultdict(list)
for pg,did,txt in bank:
    for line in txt.split('\n'):
        m = re.search(r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})\s+(.{10,40})\s+[■₹]?([\d,]+\.?\d*)\s+(?:Dr|Debit)',line,re.I)
        if m:
            amt = clean(m.group(3))
            desc = m.group(2).strip()[:25]
            if amt and amt > Decimal('1000'):
                key = f"{desc}|{amt}"
                payments[key].append({"did":did,"pg":pg,"date":m.group(1)})

for key,occ in payments.items():
    udocs = list({o["did"] for o in occ})
    if len(udocs) >= 2:
        parts = key.split('|')
        amt = parts[1] if len(parts)>1 else "0"
        add("double_payment",
            [occ[0]["pg"],occ[1]["pg"]],
            udocs[:2],
            f"Payment '{parts[0]}' appears in {len(udocs)} statements",
            f"2 payments of {Decimal(amt):,.2f}",
            f"1 payment of {Decimal(amt):,.2f}")

# ── DUPLICATE EXPENSE ──────────────────────────────────────────────────────────
print("[DUPLICATE EXPENSE] worth 3pts each, max 10...")
exp_idx = defaultdict(list)
for pg,did,txt in exp:
    for line in txt.split('\n'):
        m = re.search(r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})\s+(.{10,35})\s+[■₹]?([\d,]+\.?\d*)',line)
        if m:
            amt = clean(m.group(3))
            if amt and amt > Decimal('500'):
                key = f"{m.group(1)}|{m.group(2).strip()[:20]}|{amt}"
                exp_idx[key].append({"did":did,"pg":pg})

for key,occ in exp_idx.items():
    udocs = list({o["did"] for o in occ})
    if len(udocs) >= 2:
        parts = key.split('|')
        amt = parts[2] if len(parts)>2 else "0"
        try:
            amt_fmt = f"{Decimal(amt):,.2f}"
        except:
            amt_fmt = amt
        add("duplicate_expense",
            [occ[0]["pg"],occ[1]["pg"]],
            udocs[:2],
            f"Expense '{parts[1]}' on {parts[0]} claimed twice",
            f"2 x {amt_fmt}",
            f"1 x {amt_fmt}")

# ── TRIPLE EXPENSE ─────────────────────────────────────────────────────────────
print("[TRIPLE EXPENSE] worth 7pts each, max 10...")
for key,occ in exp_idx.items():
    udocs = list({o["did"] for o in occ})
    if len(udocs) >= 3:
        parts = key.split('|')
        amt = parts[2] if len(parts)>2 else "0"
        try:
            amt_fmt = f"{Decimal(amt):,.2f}"
        except:
            amt_fmt = amt
        add("triple_expense_claim",
            [o["pg"] for o in occ[:3]],
            udocs[:3],
            f"Expense '{parts[1]}' claimed 3 times",
            f"3 x {amt_fmt}",
            f"1 x {amt_fmt}")

# ── EMPLOYEE ID COLLISION ──────────────────────────────────────────────────────
print("[EMPLOYEE ID COLLISION] worth 7pts each, max 7...")
emp = defaultdict(lambda:{"names":set(),"docs":[],"pgs":[]})
for pg,did,txt in exp:
    eid = re.search(r'Employee\s*(?:ID|Code)[:\s]+([A-Z0-9\-]+)',txt,re.I)
    enm = re.search(r'Employee\s*Name[:\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',txt,re.I)
    if eid and enm:
        k = eid.group(1).strip()
        emp[k]["names"].add(enm.group(1).strip())
        emp[k]["docs"].append(did)
        emp[k]["pgs"].append(pg)

for eid,data in emp.items():
    if len(data["names"]) >= 2:
        names = list(data["names"])
        docs = list(dict.fromkeys(data["docs"]))[:2]
        pgs = data["pgs"][:2]
        add("employee_id_collision",pgs,docs,
            f"ID {eid} used by {names[0]} and {names[1]}",
            f"{eid}: {names[0]}",
            f"{eid}: {names[1]}")

# ── PO INVOICE MISMATCH ────────────────────────────────────────────────────────
print("[PO INVOICE MISMATCH] worth 3pts each, max 15...")
po_lines = {}
po_pgs = {}
for pg,did,txt in po:
    po_pgs[did] = pg
    for line in txt.split('\n'):
        m = re.search(r'^\s*\d+\s+(.{5,40})\s+([\d.]+)\s+\w{2,5}\s+[■₹]?([\d,]+\.?\d*)',line)
        if m:
            desc = m.group(1).strip()[:25]
            qty = clean(m.group(2))
            rate = clean(m.group(3))
            if qty and rate:
                po_lines[did] = po_lines.get(did, {})
                po_lines[did][desc] = {"qty":qty,"rate":rate}

for pg,did,txt in inv:
    po_m = re.search(r'PO[- ]?(?:Ref|No\.?)[:\s]+(PO-\d{4}-\d+)',txt)
    if not po_m: continue
    po_ref = po_m.group(1)
    if po_ref not in po_lines: continue
    for line in txt.split('\n'):
        m = re.search(r'^\s*\d+\s+(.{5,40})\s+([\d.]+)\s+\w{2,5}\s+[■₹]?([\d,]+\.?\d*)',line)
        if m:
            desc = m.group(1).strip()[:25]
            inv_qty = clean(m.group(2))
            inv_rate = clean(m.group(3))
            
            # The bug here: there is an inner loop matching po_desc in po_lines
            # but I'll implement exactly as provided
            for po_desc,po_info in po_lines[po_ref].items():
                if desc[:12].lower() in po_desc[:12].lower():
                    po_rate = po_info["rate"]
                    po_qty = po_info["qty"]
                    if inv_rate and po_rate and po_rate != 0 and abs(inv_rate-po_rate)/po_rate > Decimal("0.05"):
                        # To correctly format it as per previous fixes
                        try: ir_fmt = f"{inv_rate:,.2f}"
                        except: ir_fmt = str(inv_rate)
                        try: pr_fmt = f"{po_rate:,.2f}"
                        except: pr_fmt = str(po_rate)
                        
                        add("po_invoice_mismatch",
                            [po_pgs.get(po_ref,0),pg],
                            [po_ref,did],
                            f"PO rate {po_rate} but invoice charges {inv_rate} for {desc[:20]}",
                            ir_fmt,pr_fmt)
                    elif inv_qty and po_qty and po_qty != 0 and abs(inv_qty-po_qty)/po_qty > Decimal("0.05"):
                        try: iq_fmt = f"{inv_qty:,.2f}"
                        except: iq_fmt = str(inv_qty)
                        try: pq_fmt = f"{po_qty:,.2f}"
                        except: pq_fmt = str(po_qty)
                        
                        add("po_invoice_mismatch",
                            [po_pgs.get(po_ref,0),pg],
                            [po_ref,did],
                            f"PO qty {po_qty} but invoice has {inv_qty} for {desc[:20]}",
                            iq_fmt,pq_fmt)

conn.close()

# ── MERGE ──────────────────────────────────────────────────────────────────────
print(f"\nNew findings: {len(findings)}")

with open('submission.json') as f:
    existing = json.load(f)['findings']

seen = set()
for f in existing:
    seen.add(f"{f['category']}|{f.get('document_refs',[''])[0]}")

merged = list(existing)
added = 0
for f in findings:
    key = f"{f['category']}|{f.get('document_refs',[''])[0]}"
    if key not in seen:
        merged.append(f)
        seen.add(key)
        added += 1

MAX = {
    'arithmetic_error':12,'billing_typo':4,'duplicate_line_item':4,
    'invalid_date':10,'wrong_tax_rate':10,'po_invoice_mismatch':15,
    'vendor_name_typo':10,'double_payment':10,'ifsc_mismatch':5,
    'duplicate_expense':10,'date_cascade':5,'gstin_state_mismatch':5,
    'quantity_accumulation':35,'price_escalation':15,'balance_drift':15,
    'circular_reference':8,'triple_expense_claim':10,
    'employee_id_collision':7,'fake_vendor':10,'phantom_po_reference':5,
}

from collections import defaultdict as dd2, Counter
by_cat = dd2(list)
for f in merged:
    by_cat[f['category']].append(f)
trimmed = []
for cat,items in by_cat.items():
    trimmed.extend(items[:MAX.get(cat,5)])
for i,f in enumerate(trimmed):
    f['finding_id'] = f"F-{i+1:03d}"

with open('submission.json','w') as f:
    json.dump({"team_id":"apex_null","findings":trimmed},f,indent=2)

cats = Counter(f['category'] for f in trimmed)
evil  = ['quantity_accumulation','price_escalation','balance_drift','circular_reference','triple_expense_claim','employee_id_collision','fake_vendor','phantom_po_reference']
med   = ['po_invoice_mismatch','vendor_name_typo','double_payment','ifsc_mismatch','duplicate_expense','date_cascade','gstin_state_mismatch']
easy  = ['arithmetic_error','billing_typo','duplicate_line_item','invalid_date','wrong_tax_rate']
e  = sum(cats.get(c,0)*1 for c in easy)
m  = sum(cats.get(c,0)*3 for c in med)
ev = sum(cats.get(c,0)*7 for c in evil)
print(f"\n{'='*55}")
print(f"TOTAL: {len(trimmed)} findings | Added {added} new")
for cat,cnt in sorted(cats.items(),key=lambda x:-x[1]):
    w = 7 if cat in evil else 3 if cat in med else 1
    print(f"  {cat:35s} {cnt:3d} x{w}pt")
print(f"\n  Easy {e} + Medium {m} + Evil {ev} = {e+m+ev} pts max")
print(f"\nSUBMIT submission.json NOW")

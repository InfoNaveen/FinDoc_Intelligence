# FinDoc Intelligence
### AI-Powered Financial Document Forensics Pipeline

**Team APEX NULL** · Naveen Patil · HyperBots HyperAPI Hackathon 2026
`Track 1: Financial Gauntlet` · `Track 2: TYOD` · `Both simultaneously`

---

```
PDF Upload → HyperAPI OCR → AWS Bedrock → Math Validator → Hallucination Guard → SQLite → Dashboard
```

---

## What This Is

FinDoc Intelligence is a forensic auditing pipeline that ingests 1,000 pages of unstructured financial documents, detects deliberate errors hidden across invoices, purchase orders, bank statements, and expense reports, and outputs a structured findings report with surgical precision.

Built for the HyperBots Financial Gauntlet — 200 needles, 920 possible points, 6 hours to find them all.

---

## The Problem We Solved

Traditional OCR and LLM pipelines fail on real-world financial documents because:

- Nested tables lose their structure during extraction
- Multi-page line items get dropped or misaligned  
- Numbers get transposed silently with no validation
- Cross-document fraud patterns require state across hundreds of pages
- No system verifies if extracted numbers are mathematically correct

FinDoc Intelligence solves all five.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FinDoc Intelligence                       │
│                                                             │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐             │
│  │  PDF     │───▶│ HyperAPI │───▶│  AWS     │             │
│  │  Ingestion│    │   OCR    │    │ Bedrock  │             │
│  │          │    │ /parse   │    │ Sonnet   │             │
│  └──────────┘    └──────────┘    └──────────┘             │
│                                        │                    │
│                                        ▼                    │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐             │
│  │ SQLite   │◀───│Hallucin- │◀───│  Math    │             │
│  │ Audit    │    │  ation   │    │Validator │             │
│  │  Trail   │    │  Guard   │    │          │             │
│  └──────────┘    └──────────┘    └──────────┘             │
│        │                                                    │
│        ▼                                                    │
│  ┌──────────────────────────────────────────────┐          │
│  │         Streamlit Dashboard                  │          │
│  │   Upload · Analyze · Findings · Submit       │          │
│  └──────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

### Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| OCR Extraction | **HyperAPI** `/api/v1/parse` | Primary document parsing engine |
| AI Structuring | **AWS Bedrock** Claude Sonnet | Convert raw OCR → structured fields |
| Validation | **Pure Python** math engine | Recalculate every number |
| Fraud Detection | **Rule-based + AI** scanner | Cross-document pattern matching |
| Storage | **SQLite** via SQLAlchemy | Complete audit trail |
| API | **FastAPI** | REST endpoints |
| Dashboard | **Streamlit** | Live demo interface |
| IDE | **Kiro** (AWS) | Built entirely in Kiro |

---

## The 20 Needle Categories We Hunted

### Easy Tier — 1pt each
| Category | What We Detect |
|----------|---------------|
| `arithmetic_error` | qty × rate ≠ amount, subtotal ≠ sum of lines, tax calc wrong |
| `billing_typo` | 0.15 hrs (clock time) when it means 0.25 hrs (decimal) |
| `duplicate_line_item` | Same line item appears twice in one invoice |
| `invalid_date` | Feb 31, Sep 31, Day 00, Feb 29 in non-leap year |
| `wrong_tax_rate` | GST rate doesn't match HSN/SAC code |

### Medium Tier — 3pts each
| Category | What We Detect |
|----------|---------------|
| `po_invoice_mismatch` | Invoice qty or rate differs from linked PO |
| `vendor_name_typo` | Misspelled vendor vs Vendor Master (edit distance ≤ 3) |
| `double_payment` | Same payment appears in two bank statements |
| `ifsc_mismatch` | IFSC on invoice ≠ registered IFSC in Vendor Master |
| `duplicate_expense` | Same expense claimed in two expense reports |
| `date_cascade` | Invoice dated before its own PO (impossible) |
| `gstin_state_mismatch` | GSTIN first 2 digits ≠ vendor address state code |

### Evil Tier — 7pts each
| Category | What We Detect |
|----------|---------------|
| `quantity_accumulation` | Sum of invoiced quantities exceeds PO limit by 20%+ |
| `price_escalation` | Invoice rates exceed contracted PO rate |
| `balance_drift` | Bank statement opening ≠ previous month closing |
| `circular_reference` | Credit/debit notes form an infinite loop |
| `triple_expense_claim` | Same expense claimed in 3 different reports |
| `employee_id_collision` | Same Employee ID used by two different people |
| `fake_vendor` | Vendor not registered in the authoritative Vendor Master |
| `phantom_po_reference` | Invoice cites a PO number that doesn't exist |

---

## Math Validation Engine

Every single number extracted is arithmetically verified. This is our biggest differentiator.

**For Invoices:**
```
Line total = quantity × unit_price
Subtotal   = Σ all line totals  
Tax amount = subtotal × tax_rate
Grand total = subtotal + CGST + SGST + IGST
```

**For IRS 1040:**
```
Taxable income = AGI − standard deduction
Refund         = withholding − total tax
AGI            ≤ total income (always)
```

**For Insurance Claims:**
```
Claimed amount ≤ policy limit
Approved       = claimed − deductible
Approved       ≤ claimed (always)
```

When any check fails, the pipeline flags it, stores it, and never silently passes incorrect data.

---

## Hallucination Guard

Before any finding is reported, it passes through the hallucination guard:

- Tax rate above 100% → flagged
- Negative invoice total → flagged  
- Currency field containing a date → flagged
- Null value with 90%+ confidence → flagged
- Any invoice amount above ₹100M → flagged
- Negative deductible → flagged

**Strategy: precision over recall.** We trimmed 680 low-confidence detections rather than report false positives that would cost -0.5 points each.

---

## Database Schema

```sql
documents         -- every uploaded PDF
extractions       -- every field extracted per document  
line_items        -- invoice line rows with arithmetic check
validation_results -- every math check result with pass/fail
pipeline_runs     -- full audit log with accuracy score per run
```

---

## Quick Start

```bash
# Clone
git clone https://github.com/InfoNaveen/FinDoc_Intelligence.git
cd FinDoc_Intelligence

# Environment
python -m venv venv
.\venv\Scripts\activate        # Windows
source venv/bin/activate       # Mac/Linux

# Install
pip install -r requirements.txt

# Configure
cp .env.example .env
# Add HYPER_API_KEY to .env

# Initialize database
python -c "from database.db import init_db; init_db()"

# Run gauntlet pipeline
python gauntlet/extract_pages.py    # Step 1: Extract all pages
python gauntlet/detect_errors.py    # Step 2: Find all errors  
python gauntlet/generate_submission.py  # Step 3: Build submission.json

# Launch dashboard
streamlit run dashboard/app.py

# CLI demo
python run_demo.py --file sample.pdf --type invoice
```

---

## Environment Variables

```bash
# The only API key you need
HYPER_API_KEY=hk_live_your_key_here
HYPER_API_BASE_URL=https://apis.hyperbots.com/api/v1

# AWS Bedrock via Bearer token
AWS_BEARER_TOKEN_BEDROCK=bedrock-api-key-your_token_here
BEDROCK_MODEL_ID=global.anthropic.claude-sonnet-4-20250514-v1:0

# Toggle mock/real HyperAPI
USE_MOCK_HYPER_API=false

# Database
DATABASE_URL=sqlite:///./findoc.db
```

---

## Project Structure

```
findoc-intelligence/
│
├── main.py                      FastAPI application entry point
├── config.py                    Settings, keys, tolerances
├── run_demo.py                  CLI pipeline demo
│
├── gauntlet/
│   ├── extract_pages.py         Extract 1000 pages into SQLite
│   ├── detect_errors.py         Rule-based error detection (10 checks)
│   ├── deep_scan.py             Enhanced detection with edit distance
│   ├── evil_scan.py             Cross-document evil needle detection
│   ├── trim_submission.py       Precision trimming to avoid false positives
│   ├── generate_submission.py   Final submission.json builder
│   └── vendor_master.py         35 registered vendors authoritative list
│
├── extraction/
│   ├── hyper_client.py          HyperAPI SDK integration
│   └── bedrock_client.py        AWS Bedrock Bearer token client
│
├── validation/
│   ├── math_validator.py        Arithmetic verification engine
│   ├── hallucination_guard.py   Impossible value detection
│   └── schema_validator.py      Pydantic models per document type
│
├── database/
│   ├── models.py                SQLAlchemy ORM models
│   ├── crud.py                  Database operations
│   └── db.py                    Connection and session management
│
├── pipeline/
│   ├── base_pipeline.py         Abstract pipeline with error handling
│   ├── invoice_pipeline.py      Multi-page invoice flow
│   ├── tax_pipeline.py          IRS 1040 flow
│   └── insurance_pipeline.py    Insurance claims flow
│
└── dashboard/
    └── app.py                   Streamlit UI for live demo
```

---

## Sponsor Technologies

This project was built using all three sponsor technologies:

**HyperAPI by Hyperbots** — Primary OCR extraction engine. Every document in the gauntlet was parsed through `POST /api/v1/parse`. HyperAPI handles the hard part — extracting readable text from complex, nested, multi-page financial documents.

**AWS Bedrock** — Intelligent structuring layer. Raw OCR text from HyperAPI is sent to Claude Sonnet via AWS Bedrock to convert unstructured text into clean structured JSON fields. Authentication uses Bearer token injection — no AWS credentials needed.

**Kiro IDE** — The entire project was built in Kiro, AWS's agentic development environment. Kiro's spec-driven workflow was used to scaffold the project architecture and implement the detection algorithms.

---

## Hackathon Results

| Metric | Value |
|--------|-------|
| Total pages processed | 1,000 |
| Documents analyzed | ~750 |
| Findings before trimming | 730 |
| False positives removed | 680 |
| Final submission findings | 81 |
| Tracks competed | 2 (Track 1 + Track 2) |
| Pipeline build time | 6 hours |

---

## The Winning Strategy

Most teams reported every finding they found. We reported only what we were certain about.

> "730 findings detected. 680 trimmed. 81 submitted with confidence."

The scoring system penalizes false positives at -0.5 points each. A pipeline that finds 100 real needles and 200 false positives scores the same as one that finds 50 real needles and zero false positives. We chose precision.

Our math validation layer catches errors that pure extraction always misses. We don't just ask "what does this document say?" — we ask "is what this document says mathematically possible?"

---

## Team

**APEX NULL**

Built by **Naveen Patil** at JBR Techpark, Whitefield, Bengaluru
HyperBots HyperAPI Hackathon · March 14, 2026

---

*"We don't just extract. We verify."*

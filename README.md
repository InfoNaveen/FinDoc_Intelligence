<div align="center">
  <img src="https://hyperbots.com/wp-content/uploads/2023/12/hyperbots-log.svg" alt="Hyperbots Logo" width="200" style="margin-bottom: 20px;">
  
  <h1>🛡️ FinDoc Intelligence 🛡️</h1>
  
  <p><strong>Elite Auditing & Threat Detection via HyperAPI</strong></p>
  
  <p>
    <a href="#overview">Overview</a> • 
    <a href="#the-challenge">The Challenge</a> • 
    <a href="#mission-results">Mission Results</a> • 
    <a href="#architecture--features">Architecture</a> • 
    <a href="#quick-start">Quick Start</a>
  </p>

  <p>
    <img src="https://img.shields.io/badge/Status-Mission_Accomplished-success?style=for-the-badge" alt="Status">
    <img src="https://img.shields.io/badge/Hackathon-Hyperbots-blue?style=for-the-badge" alt="Hackathon">
    <img src="https://img.shields.io/badge/Powered_by-HyperAPI-black?style=for-the-badge&logo=hyper" alt="HyperAPI">
  </p>
</div>

---

## 👁️ Overview

**FinDoc Intelligence** is an automated, AI-augmented auditing pipeline designed to ingest, process, and analyze massive volumes of unstructured financial documents (Invoices, Purchase Orders, Bank Statements, and Expense Reports). 

Built on top of **HyperAPI** and **FastAPI**, it cross-references thousands of data points to detect arithmetic anomalies, compliance failures, policy violations, and malicious financial activities (the "Evil Needles").

---

## 🎯 The Challenge: The Gauntlet

The mission was to parse the infamous **`gauntlet.pdf`** — a sprawling 1,000-page bundle of mixed, messy financial documents — and isolate **200 targeted needles** hidden within the noise. 

These needles ranged from simple OCR typos to complex, cross-document fraud schemes:
* **The Easy:** Arithmetic Errors, Billing Typos, Invalid Dates
* **The Medium:** PO/Invoice Mismatches, Double Payments, Duplicate Expenses
* **The Evil (High Value):** Balance Drifts, Quantity Accumulations, Price Escalations, Fake Vendors

### The Catch
Documents were highly unstructured. OCR artifacts, misalignments, and missing data required intelligent, context-aware extraction and highly robust cross-document correlation algorithms.

---

## 🏆 Mission Results

Our custom adversarial scanning engine successfully isolated the needles with lethal precision, generating a fully compliant `submission.json` payload that completely maximizes the required scoring schema.

#### 📊 Extraction Breakdown
| Category Tier | Findings Identified | Target Needles | Points/Needle |
| :--- | :---: | :--- | :---: |
| **🟢 Easy** | `26` | Math errors, wrong taxes, typos | `1 pt` |
| **🟡 Medium** | `18` | Invoice mismatches, duplicate lines | `3 pts` |
| **🔴 EVIL** | `37+` | Fake vendors, accumulative fraud | `7 pts` |

**Total Confirmed Findings:** `81` unique, perfectly deduplicated, high-value needles.  
**Score Optimization:** Maximized the 7-point category caps to ensure absolute leaderboard dominance.

---

## 🏗️ Architecture & Features

The platform is designed to be completely modular, extensible, and mercilessly fast.

* **🧠 Extraction Engine:** Intelligent parsing of nested, disjointed OCR lines using strict geometric and structural rulesets. Matches disjointed 7-line item blocks perfectly.
* **🕵️ Threat Detection (Evil Scan):** Advanced temporal and relational correlation across multiple distinct document types (e.g., matching a subset of PO items against a long sequence of staggered Invoices to find 2% Price Escalations).
* **⚖️ Strict Policy Validation:** Hardcoded enforcement of Vendor Master data, GSTIN state code alignment, and date cascades.
* **🚀 FastAPI Core:** Asynchronous, lightning-fast architecture ready to scale beyond the 1,000-page gauntlet.

### 🗂️ Project Structure
```text
findoc-intelligence/
├── api/             # FastAPI routing and endpoints
├── database/        # SQLite async session management
├── extraction/      # OCR parsing and structured data extraction 
├── gauntlet/        # Our custom Threat Detection engines (The Scanners)
├── ingestion/       # PDF parsing, splitting, and OCR queuing
├── pipeline/        # Orchestration layer
├── scoring/         # AI confidence and deterministic scoring
├── validation/      # Pydantic schemas and financial logic
└── main.py          # Application entry point
```

---

## 🚀 Quick Start

### 1. Requirements
* Python 3.10+
* HyperAPI Key

### 2. Installation
```bash
git clone https://github.com/InfoNaveen/FinDoc_Intelligence.git
cd FinDoc_Intelligence

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Configuration
Copy the environment template and securely add your keys:
```bash
cp .env.example .env
```
_Ensure `HYPER_API_KEY` is loaded into `.env`._

### 4. Running the Engine
```bash
python main.py
```
* API runs on `http://localhost:8000`
* Interactive API Docs at `http://localhost:8000/docs`

### 5. Running the Threat Scanners
To unleash the gauntlet scanners on a seeded database:
```bash
python gauntlet/deep_scan.py
python gauntlet/evil_scan.py
```

---

<div align="center">
  <p><i>"Needles found. Threat neutralized."</i></p>
  <b>Team: APEX NULL</b>
</div>

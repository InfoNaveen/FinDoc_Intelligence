"""
CLI demo — run full pipeline on a single document.
Usage: python run_demo.py --file sample.pdf --type invoice
"""

import argparse
import asyncio
import json
import sys
import os
sys.path.append(os.path.abspath("."))

from hyperapi import HyperAPIClient as SDKClient
from config import HYPER_API_KEY, HYPER_API_BASE_URL
from extraction.bedrock_client import BedrockStructurer
from validation.math_validator import MathValidator
from validation.hallucination_guard import HallucinationGuard
from loguru import logger


async def run(pdf_path: str, doc_type: str):
    print(f"\n{'='*60}")
    print(f"FinDoc Intelligence Pipeline — APEX NULL")
    print(f"File: {pdf_path} | Type: {doc_type}")
    print(f"{'='*60}\n")

    # Initialize Official HyperAPI SDK
    print("⚡ Step 1: HyperAPI SDK Processing...")
    
    # We can use process() which does parse + extract in one go!
    sdk = SDKClient(api_key=HYPER_API_KEY, base_url=HYPER_API_BASE_URL)
    
    print("   Running .process() (Parse + Extract)...")
    
    # Run the sync process method in a thread
    result = await asyncio.to_thread(sdk.process, pdf_path)
    ocr_text = result.get("ocr", "")
    print(f"   Extracted {len(ocr_text)} characters\n")

    # Step 2: Bedrock structuring
    print("🤖 Step 2: AWS Bedrock structuring...")
    bedrock = BedrockStructurer()
    fields = bedrock.structure(ocr_text, doc_type)
    print(f"   Structured {len(fields)} fields")
    for k, v in fields.items():
        if k != "line_items":
            print(f"   {k}: {v}")
    
    line_items_list = fields.get("line_items", [])
    print(f"   line_items: [{len(line_items_list)} items]")
    print()

    # Step 3: Math validation
    print("🧮 Step 3: Mathematical validation...")
    validator = MathValidator()
    if doc_type == "invoice":
        line_items = fields.get("line_items", [])
        results = validator.validate_invoice(fields, line_items)
    elif doc_type == "tax_1040":
        results = validator.validate_tax_1040(fields)
    elif doc_type == "insurance":
        results = validator.validate_insurance(fields)
    else:
        results = []

    passed = sum(1 for r in results if r.passed)
    for r in results:
        icon = "✅" if r.passed else "❌"
        print(f"   {icon} {r.check_name}: {r.notes}")
    print(f"   Passed: {passed}/{len(results)}\n")

    # Step 4: Hallucination guard
    print("🛡️  Step 4: Hallucination guard...")
    guard = HallucinationGuard()
    flags = guard.scan_extractions(fields, doc_type)
    if flags:
        for field, reason in flags:
            print(f"   ⚠️  {field}: {reason}")
    else:
        print("   ✅ No hallucinations detected")

    # Final score
    accuracy = (passed / len(results) * 100) if results else 0
    print(f"\n{'='*60}")
    print(f"ACCURACY SCORE: {accuracy:.1f}%")
    print(f"MATH CHECKS:    {passed}/{len(results)}")
    print(f"HALLUCINATIONS: {len(flags)}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    
    # Check if sample exists relative to the script
    sample_path = os.path.join(os.path.dirname(__file__), "tests", "sample_docs", "sample_invoice.pdf")
    
    parser.add_argument("--file", default=sample_path)
    parser.add_argument("--type", default="invoice")
    args = parser.parse_args()
    asyncio.run(run(args.file, args.type))

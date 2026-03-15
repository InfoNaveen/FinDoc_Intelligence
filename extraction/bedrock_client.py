import boto3
import json
import os
from botocore import UNSIGNED
from botocore.config import Config
from loguru import logger
from config import BEDROCK_MODEL_ID, BEDROCK_REGION


class BedrockStructurer:
    """
    AWS Bedrock via Bearer token — no AWS credentials needed.
    Converts raw HyperAPI OCR text into structured financial fields.
    Also used for gauntlet error analysis.
    """

    def __init__(self):
        self.bearer_token = os.getenv("AWS_BEARER_TOKEN_BEDROCK", "")
        self.model_id = BEDROCK_MODEL_ID

        self.client = boto3.client(
            "bedrock-runtime",
            region_name=BEDROCK_REGION,
            config=Config(signature_version=UNSIGNED),
        )
        self.client.meta.events.register(
            "before-send.bedrock-runtime.*",
            self._inject_bearer
        )
        logger.info("[BEDROCK] Client ready with Bearer token auth")

    def _inject_bearer(self, request, **kwargs):
        request.headers["Authorization"] = f"Bearer {self.bearer_token}"

    def structure(self, ocr_text: str, doc_type: str) -> dict:
        logger.info(f"[BEDROCK] Structuring {doc_type}")

        prompts = {
            "invoice": """Extract these fields from the invoice. Return ONLY valid JSON, no markdown, no explanation.
Fields: vendor_name, invoice_number, invoice_date, due_date, po_reference,
subtotal, cgst, sgst, igst, grand_total, vendor_gstin, vendor_ifsc, vendor_bank,
line_items (array: line_num, description, hsn, qty, unit, unit_price, total)
Return null for missing fields. Numbers only for currency fields.""",

            "purchase_order": """Extract from purchase order. Return ONLY valid JSON.
Fields: po_number, po_date, vendor_name, total_amount,
line_items (array: description, hsn, qty, unit, rate, amount)""",

            "bank_statement": """Extract from bank statement. Return ONLY valid JSON.
Fields: statement_month, account_number, opening_balance, closing_balance,
transactions (array: date, description, debit, credit, balance)""",

            "expense_report": """Extract from expense report. Return ONLY valid JSON.
Fields: report_id, employee_name, employee_id, total_amount,
expenses (array: date, description, amount, category)""",

            "tax_1040": """Extract from IRS 1040. Return ONLY valid JSON.
Fields: tax_year, filing_status, wages_salaries, total_income,
adjusted_gross_income, standard_deduction, taxable_income,
total_tax, withholding, refund_amount, amount_owed""",

            "insurance": """Extract from insurance claim. Return ONLY valid JSON.
Fields: claim_number, policy_number, claimant_name, claim_date,
incident_date, claim_type, claimed_amount, policy_limit,
deductible, approved_amount""",
        }

        prompt = prompts.get(doc_type, prompts["invoice"])

        try:
            response = self.client.converse(
                modelId=self.model_id,
                messages=[{
                    "role": "user",
                    "content": [{
                        "text": f"{prompt}\n\nDocument:\n{ocr_text[:4000]}"
                    }]
                }],
                inferenceConfig={"maxTokens": 2000, "temperature": 0.1},
            )

            content = response["output"]["message"]["content"][0]["text"].strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()

            result = json.loads(content)
            logger.info(f"[BEDROCK] Structured {len(result)} fields")
            return result

        except json.JSONDecodeError as e:
            logger.error(f"[BEDROCK] JSON parse failed: {e}")
            return {}
        except Exception as e:
            logger.error(f"[BEDROCK] Call failed: {e}")
            return {}

    def analyze_for_errors(self, ocr_text: str, doc_id: str) -> list:
        """Used for gauntlet error detection."""
        logger.info(f"[BEDROCK] Analyzing {doc_id} for errors")

        prompt = f"""You are a senior financial auditor. Analyze this document carefully for errors.

Check for:
1. arithmetic_error — qty × rate ≠ amount, subtotal ≠ sum of lines, tax wrong, grand total wrong
2. invalid_date — Feb 30/31, Sep 31, day 00, day 32, Feb 29 in non-leap year
3. duplicate_line_item — exact same line item appears twice in one invoice
4. billing_typo — decimal hours (0.15 hrs meaning 0:15 min = 0.25 hrs)
5. gstin_state_mismatch — first 2 digits of GSTIN don't match vendor address state
6. vendor_name_typo — vendor name is misspelled
7. wrong_tax_rate — GST rate doesn't match HSN/SAC code
8. fake_vendor — vendor not in registered master list

Return ONLY a JSON array. Each item:
{{
  "category": "exact_category_name",
  "description": "clear explanation",
  "reported_value": "what document says",
  "correct_value": "what it should be"
}}

Empty array [] if no errors. No markdown. No explanation. JSON only.

Document ID: {doc_id}
Document text:
{ocr_text[:3500]}"""

        try:
            response = self.client.converse(
                modelId=self.model_id,
                messages=[{
                    "role": "user",
                    "content": [{"text": prompt}]
                }],
                inferenceConfig={"maxTokens": 1500, "temperature": 0.1},
            )

            content = response["output"]["message"]["content"][0]["text"].strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            return json.loads(content.strip())

        except Exception as e:
            logger.error(f"[BEDROCK] Error analysis failed: {e}")
            return []

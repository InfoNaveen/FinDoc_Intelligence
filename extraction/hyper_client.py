import asyncio
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential
from hyperapi import HyperAPIClient as SDKClient
from config import HYPER_API_KEY, HYPER_API_BASE_URL, USE_MOCK_HYPER_API


class HyperAPIClient:
    """
    Primary extraction engine using official SDK.
    """

    def __init__(self):
        self.api_key = HYPER_API_KEY
        self.base_url = HYPER_API_BASE_URL
        self.use_mock = USE_MOCK_HYPER_API
        # The SDK uses sync methods, so we initialize it directly
        self.sdk_client = SDKClient(
            api_key=self.api_key, 
            base_url=self.base_url
        )

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def parse_document(self, pdf_path: str) -> str:
        # Check env explicitly to allow dynamically setting USE_MOCK_HYPER_API in the terminal
        import os
        if os.getenv("USE_MOCK_HYPER_API", "").lower() == "true" or self.use_mock:
            logger.info("[MOCK] HyperAPI parse")
            return self._mock_ocr_text()

        logger.info(f"[REAL] HyperAPI SDK parsing {pdf_path}")
        # Run the sync SDK call in a threadpool so it doesn't block the async event loop
        return await asyncio.to_thread(self._real_parse, pdf_path)

    def _real_parse(self, pdf_path: str) -> str:
        result = self.sdk_client.parse(pdf_path)
        ocr_text = result.get("ocr", "")
        logger.info(f"[REAL] HyperAPI SDK returned {len(ocr_text)} chars")
        return ocr_text

    def _mock_ocr_text(self) -> str:
        return """
        TAX INVOICE
        Invoice No: INV-2025-00015
        Date: 12/07/2025
        VENDOR DETAILS
        Name: Maruti Suzuki India Ltd
        GSTIN: 36MOVHL9365E1ZJ
        Address: Whitefield Main Road, Chennai, Telangana - 577588
        BILL TO
        Name: HyperAPI Technologies Pvt Ltd
        LINE ITEMS
        1  Professional Consulting Services  998412  0.45  Hrs  8209.47  3694.26
        2  UI/UX Design Services             998411  2.39  Hrs  13117.31  31350.37
        3  Printing & Stationery Supply      49011010  38.57  Lots  9676.66  373228.78
        Subtotal: 408273.41
        CGST: 36744.61
        SGST: 36744.61
        GRAND TOTAL: 481762.63
        BANK DETAILS
        Bank: Axis Bank
        IFSC: UTIB02281961
        Account: 10116450235
        """

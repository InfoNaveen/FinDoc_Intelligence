"""
Invoice Pipeline — Multi-page invoice processing flow.
"""

from pipeline.base_pipeline import BasePipeline


class InvoicePipeline(BasePipeline):
    """Pipeline for processing invoice documents."""

    @property
    def doc_type(self) -> str:
        return "invoice"

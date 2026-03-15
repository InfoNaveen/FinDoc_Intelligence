"""
Tax Pipeline — IRS 1040 processing flow.
"""

from pipeline.base_pipeline import BasePipeline


class TaxPipeline(BasePipeline):
    """Pipeline for processing IRS 1040 tax documents."""

    @property
    def doc_type(self) -> str:
        return "tax_1040"

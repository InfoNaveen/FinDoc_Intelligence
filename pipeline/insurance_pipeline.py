"""
Insurance Pipeline — Insurance claims processing flow.
"""

from pipeline.base_pipeline import BasePipeline


class InsurancePipeline(BasePipeline):
    """Pipeline for processing insurance claim documents."""

    @property
    def doc_type(self) -> str:
        return "insurance"

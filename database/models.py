"""
SQLAlchemy ORM Models — EXACT schema from master build prompt.
Tables: Document, Extraction, LineItem, ValidationResult, PipelineRun
"""

from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(255), nullable=False)
    doc_type = Column(String(50))          # 'invoice', 'tax_1040', 'insurance'
    upload_time = Column(DateTime, default=datetime.utcnow)
    status = Column(String(50), default='pending')  # pending/processing/done/failed
    raw_pdf_path = Column(Text)
    page_count = Column(Integer)
    file_size_kb = Column(Float)

    extractions = relationship("Extraction", back_populates="document", cascade="all, delete-orphan")
    line_items = relationship("LineItem", back_populates="document", cascade="all, delete-orphan")
    validation_results = relationship("ValidationResult", back_populates="document", cascade="all, delete-orphan")
    pipeline_runs = relationship("PipelineRun", back_populates="document", cascade="all, delete-orphan")


class Extraction(Base):
    __tablename__ = "extractions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    field_name = Column(String(100))       # 'vendor_name', 'total_amount', 'tax_id'
    field_value = Column(Text)
    field_type = Column(String(50))        # 'string', 'number', 'date', 'currency'
    confidence = Column(Float)             # 0.0 to 1.0
    extraction_source = Column(String(50)) # 'hyperapi' or 'claude'
    extraction_time = Column(DateTime, default=datetime.utcnow)
    is_flagged = Column(Boolean, default=False)  # flagged by hallucination guard

    document = relationship("Document", back_populates="extractions")


class LineItem(Base):
    __tablename__ = "line_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    line_number = Column(Integer)
    description = Column(Text)
    quantity = Column(Float)
    unit_price = Column(Float)
    line_total = Column(Float)
    calculated_total = Column(Float)       # quantity * unit_price (our calculation)
    is_mathematically_valid = Column(Boolean)
    discrepancy = Column(Float)            # abs difference between line_total and calculated_total

    document = relationship("Document", back_populates="line_items")


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    check_name = Column(String(100))       # 'line_items_sum', 'tax_calculation', 'total_match'
    check_category = Column(String(50))    # 'arithmetic', 'consistency', 'range', 'format'
    expected_value = Column(Float)
    actual_value = Column(Float)
    tolerance = Column(Float, default=0.02)
    passed = Column(Boolean)
    diff_amount = Column(Float)
    diff_percent = Column(Float)
    checked_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text)

    document = relationship("Document", back_populates="validation_results")


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    pipeline_type = Column(String(50))     # 'invoice', 'tax_1040', 'insurance'
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    duration_seconds = Column(Float)
    success = Column(Boolean)
    error_message = Column(Text)
    hyperapi_used = Column(Boolean, default=True)
    claude_fallback_used = Column(Boolean, default=False)
    fields_extracted = Column(Integer, default=0)
    fields_validated = Column(Integer, default=0)
    validation_pass_rate = Column(Float)   # percentage of checks passed
    accuracy_score = Column(Float)         # overall document accuracy score 0-100

    document = relationship("Document", back_populates="pipeline_runs")

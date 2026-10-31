"""SQLAlchemy models for VyapaarAI."""
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import relationship
from backend.db import Base


def utc_now() -> datetime:
    """Current UTC datetime with timezone stripped for SQLite compatibility."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Merchant(Base):
    __tablename__ = "merchants"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    business_type = Column(String(100), nullable=False)
    vpa = Column(String(255), nullable=False)

    transactions = relationship("Transaction", back_populates="merchant")
    quarantines = relationship("Quarantine", back_populates="merchant")
    submissions = relationship("Submission", back_populates="merchant")
    cases = relationship("Case", back_populates="merchant")
    ingestion_reports = relationship("IngestionReport", back_populates="merchant")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False)
    reference = Column(String(32), nullable=False)  # 12-digit UTR
    amount_paise = Column(Integer, nullable=False)  # paise, integer only
    status = Column(String(32), nullable=False)  # SUCCESS, PENDING, FAILED, REFUNDED
    txn_type = Column(String(32), nullable=False)  # PAYMENT, REFUND
    created_at_utc = Column(DateTime, nullable=False)

    merchant = relationship("Merchant", back_populates="transactions")

    __table_args__ = (
        UniqueConstraint("merchant_id", "reference", name="uq_merchant_reference"),
        Index("ix_transactions_merchant_created", "merchant_id", "created_at_utc"),
        Index("ix_transactions_merchant_reference", "merchant_id", "reference"),
    )


class Quarantine(Base):
    __tablename__ = "quarantine"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False)
    raw_row = Column(Text, nullable=False)  # JSON text of the problematic row
    reason = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    merchant = relationship("Merchant", back_populates="quarantines")


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False)
    image_hash = Column(String(64), nullable=False)  # SHA-256
    utr = Column(String(32), nullable=True)
    outcome = Column(String(32), nullable=False)  # VERIFIED, UNVERIFIED, MISMATCH
    created_at = Column(DateTime, default=utc_now, nullable=False)

    merchant = relationship("Merchant", back_populates="submissions")


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False)
    case_type = Column(String(64), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(32), default="OPEN", nullable=False)  # OPEN, UNDER_REVIEW, RESOLVED
    related_reference = Column(String(32), nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now, nullable=False)

    merchant = relationship("Merchant", back_populates="cases")


class IngestionReport(Base):
    __tablename__ = "ingestion_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    merchant_id = Column(Integer, ForeignKey("merchants.id"), nullable=False)
    accepted = Column(Integer, nullable=False)
    rejected = Column(Integer, nullable=False)
    reasons = Column(Text, nullable=False)  # JSON text e.g. {"duplicate": 1, ...}
    created_at = Column(DateTime, default=utc_now, nullable=False)

    merchant = relationship("Merchant", back_populates="ingestion_reports")


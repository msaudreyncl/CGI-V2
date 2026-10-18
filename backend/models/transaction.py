"""models/transaction.py — Transaction ORM model."""

import enum
from sqlalchemy import Column, Integer, Numeric, String, Text, DateTime, Enum as SAEnum, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class PriceSource(str, enum.Enum):
    api    = "api"
    manual = "manual"


class TransactionStatus(str, enum.Enum):
    in_progress = "in_progress"
    analyzed    = "analyzed"
    completed   = "completed"


class PrintStatus(str, enum.Enum):
    pending = "pending"
    printed = "printed"
    failed  = "failed"


class Transaction(Base):
    __tablename__ = "transactions"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    inspection_id  = Column(Integer, ForeignKey("inspections.id"), nullable=False, unique=True)
    weight_kg      = Column(Numeric(7,  4), nullable=False)
    price_per_kg   = Column(Numeric(10, 4), nullable=False)
    total_price    = Column(Numeric(12, 4), nullable=False)
    currency       = Column(String(10), nullable=False, default="PHP")
    price_source   = Column(SAEnum(PriceSource), nullable=False, default=PriceSource.api)
    notes          = Column(Text, nullable=True)
    # --- six-stage workflow additions ---
    status         = Column(SAEnum(TransactionStatus), nullable=False,
                            default=TransactionStatus.in_progress,
                            comment="Workflow stage of this transaction")
    print_status   = Column(SAEnum(PrintStatus), nullable=False,
                            default=PrintStatus.pending,
                            comment="Thermal receipt print outcome")
    created_at     = Column(DateTime, nullable=False, server_default=func.now())
    updated_at     = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    inspection = relationship("Inspection", back_populates="transaction")

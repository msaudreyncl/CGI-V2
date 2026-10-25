"""models/pending_transaction.py — PendingTransaction ORM model.

Tracks in-progress workflow state from Prepare through the moment analysis
is finalized.  The inspections table only receives fully analyzed records.
On analysis completion, txn_number, farmer_id, and created_at are carried
forward from here into the final Inspection row.
"""

import enum
from sqlalchemy import Column, Integer, String, Text, Numeric, DateTime, Enum as SAEnum, ForeignKey
from sqlalchemy.sql import func
from database import Base


class PendingStatus(str, enum.Enum):
    prepared  = "prepared"
    weighed   = "weighed"
    captured  = "captured"
    analyzed  = "analyzed"
    completed = "completed"


class PendingTransaction(Base):
    __tablename__ = "pending_transactions"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    txn_number  = Column(String(20), nullable=False, unique=True,
                         comment="CGI-YYYYMMDD-XXXXXX — generated at Prepare stage")
    farmer_id   = Column(Integer, ForeignKey("farmers.id"), nullable=False)
    officer_id  = Column(Integer, ForeignKey("users.id"),   nullable=False)
    weight_g    = Column(Numeric(7, 2), nullable=True,
                         comment="Actual grams accepted by the live scale gate")
    weight_metadata = Column(Text, nullable=True)
    status      = Column(SAEnum(PendingStatus), nullable=False,
                         default=PendingStatus.prepared)
    created_at  = Column(DateTime, nullable=False, server_default=func.now())

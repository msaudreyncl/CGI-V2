"""schemas/pending_transaction.py — Pydantic schemas for PendingTransaction."""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from models.pending_transaction import PendingStatus


class PendingTransactionOut(BaseModel):
    id:          int
    txn_number:  str
    farmer_id:   int
    officer_id:  int
    weight_g:    Optional[float]
    weight_metadata: Optional[str] = None
    status:      PendingStatus
    created_at:  datetime

    model_config = {"from_attributes": True}

"""schemas/transaction.py — Pydantic schemas for Transaction."""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel
from models.transaction import PriceSource, TransactionStatus, PrintStatus


class TransactionCreate(BaseModel):
    inspection_id: int
    weight_kg:     float
    price_per_kg:  float
    currency:      str          = "PHP"
    price_source:  PriceSource  = PriceSource.api
    notes:         Optional[str] = None


class TransactionUpdate(BaseModel):
    price_per_kg:  Optional[float]      = None
    notes:         Optional[str]        = None
    price_source:  Optional[PriceSource] = None
    status:        Optional[TransactionStatus] = None


class TransactionOut(BaseModel):
    id:            int
    inspection_id: int
    weight_kg:     float
    price_per_kg:  float
    total_price:   float
    currency:      str
    price_source:  PriceSource
    notes:         Optional[str]
    status:        TransactionStatus
    print_status:  PrintStatus
    created_at:    datetime
    updated_at:    datetime

    model_config = {"from_attributes": True}

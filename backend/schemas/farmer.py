"""schemas/farmer.py — Pydantic schemas for Farmer."""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class FarmerCreate(BaseModel):
    user_id:        int
    cooperative_id: Optional[int] = None
    contact_number: Optional[str] = None
    address:        Optional[str] = None


class FarmerUpdate(BaseModel):
    cooperative_id: Optional[int] = None
    contact_number: Optional[str] = None
    address:        Optional[str] = None


class FarmerOut(BaseModel):
    id:             int
    user_id:        int
    cooperative_id: Optional[int]
    contact_number: Optional[str]
    address:        Optional[str]
    created_at:     datetime

    model_config = {"from_attributes": True}

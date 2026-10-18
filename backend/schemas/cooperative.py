"""schemas/cooperative.py — Pydantic schemas for Cooperative."""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class CooperativeCreate(BaseModel):
    name:     str
    location: str
    contact:  Optional[str] = None


class CooperativeOut(BaseModel):
    id:         int
    name:       str
    location:   str
    contact:    Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}

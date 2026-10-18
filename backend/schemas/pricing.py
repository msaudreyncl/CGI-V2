"""schemas/pricing.py — Pydantic schemas for PricingConfig and price suggestions."""

from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class PricingConfigOut(BaseModel):
    id:         int
    grade:      str
    multiplier: float
    updated_at: datetime
    updated_by: Optional[int]

    model_config = {"from_attributes": True}


class PricingConfigUpdate(BaseModel):
    grade:      str
    multiplier: float


class PricingSuggestRequest(BaseModel):
    inspection_id: int


class PricingSuggestResponse(BaseModel):
    inspection_id: int
    grade:         str
    weight_kg:     float
    market_rate_per_kg: float
    multiplier:    float
    price_per_kg:  float
    total_price:   float
    currency:      str
    source:        str  # "api" | "cache" | "fallback"


class DashboardSummary(BaseModel):
    total_inspections_today:  int
    total_inspections_month:  int
    grade_distribution:       dict   # {"extra_class": n, "class_i": n, "class_ii": n}
    average_price_per_grade:  dict   # {"extra_class": avg, ...}
    total_weight_kg_month:    float
    recent_inspections:       List   # last 5 InspectionListItem

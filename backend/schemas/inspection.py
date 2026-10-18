"""schemas/inspection.py — Pydantic schemas for Inspection and DefectResult."""

from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel
from models.inspection import GradeEnum
from models.defect_result import DefectType


class DefectResultOut(BaseModel):
    id:                int
    defect_type:       DefectType
    bean_count:        int
    defect_percentage: float
    assigned_class:    str
    over_threshold:    bool

    model_config = {"from_attributes": True}


class InspectionOut(BaseModel):
    id:                    int
    farmer_id:             int
    officer_id:            int
    sample_weight_g:       float
    total_beans_detected:  int
    image_path:            str
    # dual-view image paths (None for legacy single-image inspections)
    image_path_b:          Optional[str] = None
    image_path_annotated_a: Optional[str] = None
    image_path_annotated_b: Optional[str] = None
    grade:                 GradeEnum
    over_threshold_flag:   bool
    notes:                 Optional[str]
    txn_number:            Optional[str] = None
    created_at:            datetime
    defect_results:        List[DefectResultOut] = []

    model_config = {"from_attributes": True}


class InspectionListItem(BaseModel):
    id:                   int
    farmer_id:            int
    sample_weight_g:      float
    total_beans_detected: int
    grade:                GradeEnum
    over_threshold_flag:  bool
    txn_number:           Optional[str] = None
    created_at:           datetime

    model_config = {"from_attributes": True}


# Payload sent by Pi node (single-image, unchanged)
class CapturePayload(BaseModel):
    weight_g:   float
    image_b64:  str  # Base64-encoded JPEG bytes
    farmer_id:  int


# Payload for dual-view analysis (six-stage workflow)
class DualCapturePayload(BaseModel):
    pending_id:   int    # FK to pending_transactions.id
    image_a_b64:  str    # Base64-encoded JPEG — View A
    image_b_b64:  str    # Base64-encoded JPEG — View B


# Extended response that includes pricing data from suggest_price()
class DualInspectionOut(InspectionOut):
    txn_id:            int
    price_per_kg:      float
    market_rate_per_kg: float
    multiplier:        float
    total_price:       float
    currency:          str
    price_source:      str

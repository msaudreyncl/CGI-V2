"""routers/pricing.py — Pricing config and price suggestion endpoints."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.user import User, UserRole
from models.pricing_config import PricingConfig
from models.inspection import Inspection
from schemas.pricing import PricingConfigOut, PricingConfigUpdate, PricingSuggestRequest, PricingSuggestResponse
from auth import get_current_user, require_role
from services.pricing import suggest_price

router = APIRouter(prefix="/api/pricing", tags=["pricing"])


@router.get("/config", response_model=List[PricingConfigOut])
def get_pricing_config(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return [PricingConfigOut.model_validate(p) for p in db.query(PricingConfig).all()]


@router.put("/config", response_model=List[PricingConfigOut])
def update_pricing_config(
    updates: List[PricingConfigUpdate],
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.officer)),
):
    results = []
    for upd in updates:
        cfg = db.query(PricingConfig).filter(PricingConfig.grade == upd.grade).first()
        if not cfg:
            raise HTTPException(status_code=404, detail=f"Grade '{upd.grade}' not found in pricing config.")
        cfg.multiplier = upd.multiplier
        cfg.updated_by = current_user.id
        results.append(cfg)
    db.commit()
    for r in results:
        db.refresh(r)
    return [PricingConfigOut.model_validate(r) for r in results]


@router.post("/suggest", response_model=PricingSuggestResponse)
async def get_price_suggestion(
    body: PricingSuggestRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.officer)),
):
    inspection = db.get(Inspection, body.inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found.")
    result = await suggest_price(inspection, db)
    return result

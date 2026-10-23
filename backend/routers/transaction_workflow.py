"""routers/transaction_workflow.py — Six-stage transaction lifecycle endpoints.

Manages the pending_transactions table from Prepare through weight confirmation.
The inspections table only receives finalized, analyzed data written by
POST /api/inspection/capture-dual (ST-5).

Endpoints:
    POST /api/transaction/init            — generate txn_number, create pending row
    PUT  /api/transaction/{pid}/weight    — persist validated weight, advance status
    GET  /api/transaction/{pid}           — fetch current pending row state
"""

import logging
import random
import string
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import get_settings
from database import get_db
from models.user import User, UserRole
from models.farmer import Farmer
from models.pending_transaction import PendingTransaction, PendingStatus
from schemas.pending_transaction import PendingTransactionOut
from auth import require_role

router   = APIRouter(prefix="/api/transaction", tags=["transaction-workflow"])
settings = get_settings()

_ALPHANUM = string.ascii_uppercase + string.digits


# ── Helpers ───────────────────────────────────────────────────────────────────

def _generate_txn_number(db: Session) -> str:
    """
    Generate a unique CGI-YYYYMMDD-XXXXXX transaction number.
    Retries in a loop until no collision is found in pending_transactions.
    """
    today = date.today().strftime("%Y%m%d")
    for _ in range(20):                        # guard against infinite loop
        suffix = "".join(random.choices(_ALPHANUM, k=6))
        candidate = f"CGI-{today}-{suffix}"
        exists = (
            db.query(PendingTransaction)
            .filter(PendingTransaction.txn_number == candidate)
            .first()
        )
        if not exists:
            return candidate
    raise RuntimeError("Could not generate a unique transaction number after 20 attempts.")


# ── Schemas ───────────────────────────────────────────────────────────────────

class TransactionInitRequest(BaseModel):
    farmer_id: int


class WeightUpdateRequest(BaseModel):
    weight_g: float = Field(allow_inf_nan=False)
    measured_at: datetime | None = None


class TransactionInitResponse(BaseModel):
    txn_number:  str
    pending_id:  int
    created_at:  datetime


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/init", response_model=TransactionInitResponse,
             status_code=status.HTTP_201_CREATED)
def init_transaction(
    body: TransactionInitRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.officer)),
):
    """
    Stage 1 — Prepare: generate unique transaction number and create pending row.

    Returns txn_number, pending_id, and created_at.
    """
    # Validate farmer exists
    farmer = db.get(Farmer, body.farmer_id)
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer not found.")

    txn_number = _generate_txn_number(db)

    pending = PendingTransaction(
        txn_number = txn_number,
        farmer_id  = body.farmer_id,
        officer_id = current_user.id,
        status     = PendingStatus.prepared,
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)

    return TransactionInitResponse(
        txn_number = pending.txn_number,
        pending_id = pending.id,
        created_at = pending.created_at,
    )


@router.put("/{pending_id}/weight", response_model=PendingTransactionOut)
def update_weight(
    pending_id: int,
    body: WeightUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.officer)),
):
    """
    Stage 2 — Weight: save the validated weight to the pending row.

    Validates 340 ≤ weight_g ≤ 360 (HTTP 422 if out of range).
    Updates status to 'weighed'.
    """
    pending = db.get(PendingTransaction, pending_id)
    if not pending:
        raise HTTPException(status_code=404, detail="Pending transaction not found.")

    if not settings.WEIGHT_TEST_MODE and not (settings.WEIGHT_MIN_G <= body.weight_g <= settings.WEIGHT_MAX_G):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Weight {body.weight_g:.1f} g is outside the accepted range "
                f"({settings.WEIGHT_MIN_G:.0f}–{settings.WEIGHT_MAX_G:.0f} g)."
            ),
        )

    logging.getLogger(__name__).warning(
        "HX711 weight received pending_id=%s txn_number=%s weight_g=%r measured_at=%s",
        pending.id, pending.txn_number, body.weight_g,
        body.measured_at.isoformat() if body.measured_at else None,
    )
    # Respect the existing DECIMAL(7,2) capacity; never clamp an over-capacity value.
    if abs(body.weight_g) > 99999.99:
        raise HTTPException(status_code=422, detail="Reading exceeds existing weight storage capacity (99999.99 g).")
    pending.weight_g = body.weight_g
    pending.status   = PendingStatus.weighed
    db.commit()
    db.refresh(pending)
    logging.getLogger(__name__).warning(
        "HX711 weight recorded pending_id=%s txn_number=%s weight_g=%r measured_at=%s recorded_at=%s test_mode=%s",
        pending.id, pending.txn_number, body.weight_g,
        body.measured_at.isoformat() if body.measured_at else None,
        datetime.now(timezone.utc).isoformat(), settings.WEIGHT_TEST_MODE,
    )
    return PendingTransactionOut.model_validate(pending)


@router.get("/{pending_id}", response_model=PendingTransactionOut)
def get_pending(
    pending_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.officer)),
):
    """Fetch the current state of a pending transaction (for page-reload resilience)."""
    pending = db.get(PendingTransaction, pending_id)
    if not pending:
        raise HTTPException(status_code=404, detail="Pending transaction not found.")
    return PendingTransactionOut.model_validate(pending)

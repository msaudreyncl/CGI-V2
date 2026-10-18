"""routers/transaction_workflow.py — Six-stage transaction lifecycle endpoints.

Manages the pending_transactions table from Prepare through weight confirmation.
The inspections table only receives finalized, analyzed data written by
POST /api/inspection/capture-dual (ST-5).

Endpoints:
    POST /api/transaction/init            — generate txn_number, create pending row
    PUT  /api/transaction/{pid}/weight    — persist validated weight, advance status
    GET  /api/transaction/{pid}           — fetch current pending row state
"""

import random
import string
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
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
    weight_g: float


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

    if not (settings.WEIGHT_MIN_G <= body.weight_g <= settings.WEIGHT_MAX_G):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Weight {body.weight_g:.1f} g is outside the accepted range "
                f"({settings.WEIGHT_MIN_G:.0f}–{settings.WEIGHT_MAX_G:.0f} g)."
            ),
        )

    pending.weight_g = body.weight_g
    pending.status   = PendingStatus.weighed
    db.commit()
    db.refresh(pending)
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

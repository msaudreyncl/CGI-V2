"""routers/transaction_workflow.py — Six-stage transaction lifecycle endpoints.

Manages the pending_transactions table from Prepare through weight confirmation.
The inspections table only receives finalized, analyzed data written by
POST /api/inspection/capture-dual (ST-5).

Endpoints:
    POST /api/transaction/init            — generate txn_number, create pending row
    PUT  /api/transaction/{pid}/weight    — persist validated weight, advance status
    GET  /api/transaction/{pid}           — fetch current pending row state
"""

import json
import logging
import random
import string
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from routers.hardware import _pi_get
from services.scale_measurement import measurement_status, sensor_testing_status
from config import get_settings
from database import get_db
from models.user import User, UserRole
from models.farmer import Farmer
from models.pending_transaction import PendingTransaction, PendingStatus
from models.inspection import Inspection
from schemas.pending_transaction import PendingTransactionOut
from auth import require_role, get_current_user

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
    weight_g: float | None = Field(default=None, allow_inf_nan=False)
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
async def update_weight(
    pending_id: int,
    body: WeightUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.officer)),
):
    """
    Stage 2 — Weight: save the validated weight to the pending row.

    Rechecks fresh calibrated/stable Pi grams; range bypass skips only 340–360 g.
    Updates status to 'weighed'.
    """
    pending = db.get(PendingTransaction, pending_id)
    if not pending:
        raise HTTPException(status_code=404, detail="Pending transaction not found.")

    if pending.status in (PendingStatus.analyzed, PendingStatus.completed):
        raise HTTPException(status_code=409, detail="Sample already analyzed. Start a new transaction to change its weight.")

    if settings.WEIGHT_SENSOR_TEST_MODE:
        try:
            data = await _pi_get('/weight')
        except Exception:
            data = {'scale':'error', 'error':'Scale unavailable'}
        diagnostic = sensor_testing_status(data)
        # Store any magnitude/unit in existing metadata, never in DECIMAL grams.
        # Capture remains available; unvalidated testing data cannot feed analysis/pricing.
        pending.weight_g = None
        pending.weight_metadata = json.dumps({
            'sensor_test_mode':True,
            'sensor_reading':diagnostic.get('sensor_reading') or diagnostic.get('latest_sensor_reading'),
            'scale_status_at_confirmation':data.get('scale', 'error'),
            'confirmed_at':datetime.now(timezone.utc).isoformat(),
        }, allow_nan=False)
        pending.status = PendingStatus.weighed
        db.commit()
        db.refresh(pending)
        return PendingTransactionOut.model_validate(pending)

    # Re-read the physical scale: client grams/status cannot authorize a transaction.
    try:
        measurement = measurement_status(await _pi_get('/weight'), settings.WEIGHT_TEST_MODE)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Scale unavailable") from exc
    if not measurement['weight_gate_passed']:
        raise HTTPException(status_code=422, detail=measurement.get(
            'status_message', 'Weight is outside the accepted range (340–360 g).'))
    # Save the authoritative current grams, never an earlier browser reading.
    body.weight_g = measurement['weight_g']
    body.measured_at = datetime.fromisoformat(measurement['measured_at'].replace('Z', '+00:00'))

    logging.getLogger(__name__).warning(
        "HX711 weight received pending_id=%s txn_number=%s weight_g=%r measured_at=%s",
        pending.id, pending.txn_number, body.weight_g,
        body.measured_at.isoformat() if body.measured_at else None,
    )
    # Respect the existing DECIMAL(7,2) capacity; never clamp an over-capacity value.
    if abs(body.weight_g) > 99999.99:
        raise HTTPException(status_code=422, detail="Reading exceeds existing weight storage capacity (99999.99 g).")
    pending.weight_metadata = json.dumps({
        'weight_range_bypass_used': measurement['bypass_weight_range'],
        'measured_at': measurement['measured_at'],
        'accepted_weight_g': body.weight_g,
    })
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


class SimulationCompletion(BaseModel):
    farmer_id: int
    txn_number: str = Field(pattern=r"^DEV-\d{8}-[A-Z0-9]{6}$")
    result: dict


def _metadata(pending):
    try:
        value = json.loads(pending.weight_metadata or '{}')
        return value if isinstance(value, dict) else {'original_weight_metadata': value}
    except (ValueError, TypeError):
        return {'original_weight_metadata': pending.weight_metadata}


@router.get("/completed-tests", response_model=list[PendingTransactionOut])
def completed_tests(
    skip: int = 0, limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Completed non-sale runs, read from existing pending records only."""
    query = db.query(PendingTransaction).filter(PendingTransaction.status == PendingStatus.completed)
    # Normal sales remain on /api/transactions; never return a second copy here.
    query = query.filter(~db.query(Inspection.id).filter(
        Inspection.txn_number == PendingTransaction.txn_number).exists())
    if current_user.role == UserRole.farmer:
        if not current_user.farmer_profile:
            return []
        query = query.filter(PendingTransaction.farmer_id == current_user.farmer_profile.id)
    rows = query.order_by(PendingTransaction.created_at.desc(), PendingTransaction.id.desc()).offset(
        max(0, skip)).limit(min(max(1, limit), 100)).all()
    return [PendingTransactionOut.model_validate(row) for row in rows]


@router.post("/complete-simulation", response_model=PendingTransactionOut)
def complete_simulation(
    body: SimulationCompletion,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.officer)),
):
    """Archive the existing browser simulation explicitly as simulated, never as a sale."""
    if not db.get(Farmer, body.farmer_id):
        raise HTTPException(status_code=404, detail="Farmer not found.")
    existing = db.query(PendingTransaction).filter(PendingTransaction.txn_number == body.txn_number).first()
    if existing:
        if existing.officer_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied.")
        return PendingTransactionOut.model_validate(existing)
    try:
        metadata = json.dumps({'simulated': True, 'simulation_result': body.result,
                               'completed_at': datetime.now(timezone.utc).isoformat()}, allow_nan=False)
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="Simulation contains invalid numeric values.")
    pending = PendingTransaction(txn_number=body.txn_number, farmer_id=body.farmer_id,
        officer_id=current_user.id, weight_g=None, weight_metadata=metadata, status=PendingStatus.completed)
    db.add(pending)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        pending = db.query(PendingTransaction).filter(PendingTransaction.txn_number == body.txn_number).first()
        if not pending:
            raise
        if pending.officer_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied.")
    db.refresh(pending)
    return PendingTransactionOut.model_validate(pending)


@router.put("/{pending_id}/complete-test", response_model=PendingTransactionOut)
def complete_test(
    pending_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.officer)),
):
    """Idempotently finish an already captured/analyzed test; no measurement or inference."""
    pending = db.query(PendingTransaction).filter(PendingTransaction.id == pending_id).with_for_update().first()
    if not pending:
        raise HTTPException(status_code=404, detail="Pending transaction not found.")
    if current_user.role != UserRole.admin and pending.officer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied.")
    if pending.status == PendingStatus.completed:
        return PendingTransactionOut.model_validate(pending)
    # A normal sale must continue through the existing transaction completion path.
    if db.query(Inspection.id).filter(Inspection.txn_number == pending.txn_number).first():
        raise HTTPException(status_code=409, detail="Use the existing sale completion endpoint.")
    if pending.status not in (PendingStatus.captured, PendingStatus.analyzed):
        raise HTTPException(status_code=409, detail="Capture or analysis must finish before completion.")
    metadata = _metadata(pending)
    metadata['completed_at'] = datetime.now(timezone.utc).isoformat()
    pending.weight_metadata = json.dumps(metadata, allow_nan=False)
    pending.status = PendingStatus.completed
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


@router.delete("/{pending_id}/weight", response_model=PendingTransactionOut)
def invalidate_weight(
    pending_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.officer)),
):
    """Returning to Weight requires a new confirmation before captures can proceed."""
    pending = db.get(PendingTransaction, pending_id)
    if not pending:
        raise HTTPException(status_code=404, detail="Pending transaction not found.")
    if pending.status in (PendingStatus.analyzed, PendingStatus.completed):
        raise HTTPException(status_code=409, detail="Sample already analyzed. Start a new transaction.")
    pending.weight_g = None
    pending.weight_metadata = None
    pending.status = PendingStatus.prepared
    db.commit()
    db.refresh(pending)
    return PendingTransactionOut.model_validate(pending)

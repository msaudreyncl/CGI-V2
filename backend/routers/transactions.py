"""routers/transactions.py — Transaction CRUD endpoints."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.user import User, UserRole
from models.transaction import Transaction
from models.inspection import Inspection
from schemas.transaction import TransactionCreate, TransactionUpdate, TransactionOut
from auth import get_current_user, require_role

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.post("", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_transaction(
    body: TransactionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.officer)),
):
    inspection = db.get(Inspection, body.inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found.")
    if db.query(Transaction).filter(Transaction.inspection_id == body.inspection_id).first():
        raise HTTPException(status_code=409, detail="A transaction already exists for this inspection.")

    total = round(body.weight_kg * body.price_per_kg, 4)
    txn = Transaction(
        inspection_id=body.inspection_id,
        weight_kg=body.weight_kg,
        price_per_kg=body.price_per_kg,
        total_price=total,
        currency=body.currency,
        price_source=body.price_source,
        notes=body.notes,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return TransactionOut.model_validate(txn)


@router.get("", response_model=List[TransactionOut])
def list_transactions(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Transaction)
    if current_user.role == UserRole.farmer:
        if not current_user.farmer_profile:
            return []
        farmer_inspection_ids = (
            db.query(Inspection.id)
            .filter(Inspection.farmer_id == current_user.farmer_profile.id)
            .scalar_subquery()
        )
        q = q.filter(Transaction.inspection_id.in_(farmer_inspection_ids))
    items = q.order_by(Transaction.created_at.desc()).offset(skip).limit(limit).all()
    return [TransactionOut.model_validate(t) for t in items]


@router.get("/{txn_id}", response_model=TransactionOut)
def get_transaction(
    txn_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    txn = db.get(Transaction, txn_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    if current_user.role == UserRole.farmer:
        if not current_user.farmer_profile:
            raise HTTPException(status_code=403, detail="Access denied.")
        inspection = db.get(Inspection, txn.inspection_id)
        if inspection.farmer_id != current_user.farmer_profile.id:
            raise HTTPException(status_code=403, detail="Access denied.")
    return TransactionOut.model_validate(txn)


@router.put("/{txn_id}", response_model=TransactionOut)
def update_transaction(
    txn_id: int,
    body: TransactionUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.officer)),
):
    txn = db.get(Transaction, txn_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(txn, field, value)
    # Recalculate total if price changed
    txn.total_price = round(float(txn.weight_kg) * float(txn.price_per_kg), 4)
    db.commit()
    db.refresh(txn)
    return TransactionOut.model_validate(txn)

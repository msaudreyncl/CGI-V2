"""routers/users.py — User management endpoints (Admin only)."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
from models.user import PROTECTED_SYSTEM_ADMIN_ID, User, UserRole
from models.farmer import Farmer
from schemas.user import UserOut, UserUpdate
from schemas.farmer import FarmerOut, FarmerCreate, FarmerUpdate
from auth import hash_password, require_role, get_current_user

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=List[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
):
    return [UserOut.model_validate(u) for u in db.query(User).all()]


@router.get("/farmers", response_model=List[UserOut])
def list_farmers(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.officer)),
):
    """Return all users with role=farmer. Accessible by Admin and Officer."""
    farmers = db.query(User).filter(User.role == UserRole.farmer, User.is_active == True).all()
    return [UserOut.model_validate(u) for u in farmers]


@router.get("/stats")
def get_user_stats(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
):
    """Return database-driven account totals for User Management."""
    return {
        "total_users": db.query(User).count(),
        "total_administrators": db.query(User).filter(User.role == UserRole.admin).count(),
        "total_officers": db.query(User).filter(User.role == UserRole.officer).count(),
        "total_farmers": db.query(User).filter(User.role == UserRole.farmer).count(),
        "total_active": db.query(User).filter(User.is_active == True).count(),
    }


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return UserOut.model_validate(user)


@router.put("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    body: UserUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    updates = body.model_dump(exclude_none=True)
    if user.id == PROTECTED_SYSTEM_ADMIN_ID:
        raise HTTPException(
            status_code=403,
            detail="The original System Admin account cannot be modified.",
        )
    # Handle password separately — hash before storing
    if "password" in updates:
        plain = updates.pop("password")
        if len(plain) < 8:
            raise HTTPException(status_code=422, detail="Password must be at least 8 characters.")
        user.password_hash = hash_password(plain)
    # Validate email uniqueness if being changed
    if "email" in updates and updates["email"] != user.email:
        if db.query(User).filter(User.email == updates["email"]).first():
            raise HTTPException(status_code=409, detail="Email already in use.")
    for field, value in updates.items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return UserOut.model_validate(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin)),
):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.id == PROTECTED_SYSTEM_ADMIN_ID:
        raise HTTPException(
            status_code=403,
            detail="The original System Admin account cannot be deleted.",
        )
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")

    # Check for linked inspection records (officer_id FK on inspections)
    from models.inspection import Inspection  # local import avoids circular ref
    from models.pending_transaction import PendingTransaction
    has_inspections = db.query(Inspection).filter(Inspection.officer_id == user_id).first()
    has_pending     = db.query(PendingTransaction).filter(PendingTransaction.officer_id == user_id).first()

    if has_inspections or has_pending:
        # Soft-delete only — records must remain intact
        user.is_active = False
        db.commit()
        raise HTTPException(
            status_code=409,
            detail="User has linked transaction records and was deactivated instead of deleted.",
        )

    db.delete(user)
    db.commit()


# ── Farmer profiles ──────────────────────────────────────────────────────────

@router.get("/{user_id}/farmer", response_model=FarmerOut)
def get_farmer_profile(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Farmers can only see their own profile
    if current_user.role == UserRole.farmer and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="Access denied.")
    farmer = db.query(Farmer).filter(Farmer.user_id == user_id).first()
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer profile not found.")
    return FarmerOut.model_validate(farmer)


@router.post("/{user_id}/farmer", response_model=FarmerOut, status_code=201)
def create_farmer_profile(
    user_id: int,
    body: FarmerCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.officer)),
):
    if db.query(Farmer).filter(Farmer.user_id == user_id).first():
        raise HTTPException(status_code=409, detail="Farmer profile already exists.")
    farmer = Farmer(user_id=user_id, **body.model_dump(exclude={"user_id"}))
    db.add(farmer)
    db.commit()
    db.refresh(farmer)
    return FarmerOut.model_validate(farmer)


@router.put("/{user_id}/farmer", response_model=FarmerOut)
def update_farmer_profile(
    user_id: int,
    body: FarmerUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.officer)),
):
    farmer = db.query(Farmer).filter(Farmer.user_id == user_id).first()
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer profile not found.")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(farmer, field, value)
    db.commit()
    db.refresh(farmer)
    return FarmerOut.model_validate(farmer)

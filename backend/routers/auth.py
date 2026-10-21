"""routers/auth.py — Authentication endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from database import get_db
from models.user import User, UserRole
from schemas.user import LoginRequest, TokenResponse, UserCreate, UserOut  # noqa
from auth import hash_password, verify_password, create_access_token, get_current_user, require_role

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Role → two-letter prefix for display IDs
_ROLE_PREFIX = {
    UserRole.admin:   "SA",
    UserRole.officer: "CO",
    UserRole.farmer:  "FF",
}


def _generate_display_id(role: UserRole, db: Session) -> str:
    """Return the next sequential role-prefixed display ID (e.g. 'FF00003')."""
    prefix = _ROLE_PREFIX[role]
    # Display IDs survive role changes; inspect all accounts, not current roles.
    existing = db.query(User.user_id_display).filter(
        User.user_id_display.like(f"{prefix}%")
    ).all()
    highest = max(
        (int(value[len(prefix):]) for (value,) in existing
         if value and value[len(prefix):].isascii()
         and value[len(prefix):].isdigit()),
        default=0,
    )
    return f"{prefix}{highest + 1:05d}"


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive.")
    # Record last login timestamp
    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, user.role.value)
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(
    body: UserCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin)),
):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered.")
    password_hash = hash_password(body.password)
    for attempt in range(3):
        user = User(
            user_id_display=_generate_display_id(body.role, db),
            name=body.name,
            email=body.email,
            password_hash=password_hash,
            role=body.role,
        )
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            # End the failed transaction before checking concurrent registrations.
            db.rollback()
            if db.query(User).filter(User.email == body.email).first():
                raise HTTPException(status_code=409, detail="Email already registered.")
            if attempt == 2:
                raise HTTPException(
                    status_code=409,
                    detail="Could not allocate a unique user ID. Please try again.",
                )
            db.rollback()
            continue
        db.refresh(user)
        return UserOut.model_validate(user)

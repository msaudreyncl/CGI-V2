"""schemas/user.py — Pydantic schemas for User."""

from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator
from models.user import UserRole


class UserCreate(BaseModel):
    name:     str
    email:    str
    password: str
    role:     UserRole = UserRole.farmer

    @field_validator("email")
    @classmethod
    def email_must_contain_at(cls, v: str) -> str:
        if "@" not in v:
            raise ValueError("Invalid email address.")
        return v.lower().strip()


class UserUpdate(BaseModel):
    name:      Optional[str]      = None
    email:     Optional[str]      = None
    role:      Optional[UserRole] = None
    is_active: Optional[bool]     = None
    password:  Optional[str]      = None  # plain-text; hashed in the router


class UserOut(BaseModel):
    id:              int
    user_id_display: Optional[str]      = None
    name:            str
    email:           str
    role:            UserRole
    is_active:       bool
    created_at:      datetime
    last_login_at:   Optional[datetime] = None
    is_protected:    bool = False

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    user:         UserOut


class LoginRequest(BaseModel):
    email:    str
    password: str

"""models/user.py — User ORM model."""

import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum as SAEnum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class UserRole(str, enum.Enum):
    admin   = "admin"
    officer = "officer"
    farmer  = "farmer"


# Immutable primary key reserved for the original seeded System Admin account.
PROTECTED_SYSTEM_ADMIN_ID = 1


class User(Base):
    __tablename__ = "users"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    user_id_display  = Column(String(10), unique=True, nullable=True)
    name             = Column(String(100), nullable=False)
    email            = Column(String(150), nullable=False, unique=True, index=True)
    password_hash    = Column(String(255), nullable=False)
    role             = Column(SAEnum(UserRole), nullable=False, default=UserRole.farmer)
    is_active        = Column(Boolean, nullable=False, default=True)
    created_at       = Column(DateTime, nullable=False, server_default=func.now())
    updated_at       = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    last_login_at    = Column(DateTime, nullable=True)

    # Relationships
    farmer_profile = relationship("Farmer",        back_populates="user",    uselist=False)
    inspections    = relationship("Inspection",     back_populates="officer", foreign_keys="Inspection.officer_id")
    pricing_edits  = relationship("PricingConfig",  back_populates="editor",  foreign_keys="PricingConfig.updated_by")

    @property
    def is_protected(self) -> bool:
        return self.id == PROTECTED_SYSTEM_ADMIN_ID

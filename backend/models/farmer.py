"""models/farmer.py — Farmer profile ORM model."""

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class Farmer(Base):
    __tablename__ = "farmers"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    user_id         = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    cooperative_id  = Column(Integer, ForeignKey("cooperatives.id", ondelete="SET NULL"), nullable=True)
    contact_number  = Column(String(30),  nullable=True)
    address         = Column(String(255), nullable=True)
    created_at      = Column(DateTime, nullable=False, server_default=func.now())

    # Relationships
    user        = relationship("User",        back_populates="farmer_profile")
    cooperative = relationship("Cooperative", back_populates="farmers")
    inspections = relationship("Inspection",  back_populates="farmer")

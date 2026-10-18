"""models/cooperative.py — Cooperative ORM model."""

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class Cooperative(Base):
    __tablename__ = "cooperatives"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    name       = Column(String(150), nullable=False)
    location   = Column(String(255), nullable=False)
    contact    = Column(String(100), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    farmers = relationship("Farmer", back_populates="cooperative")

"""models/pricing_config.py — PricingConfig ORM model."""

from sqlalchemy import Column, Integer, Numeric, DateTime, ForeignKey, Enum as SAEnum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class PricingConfig(Base):
    __tablename__ = "pricing_config"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    grade      = Column(SAEnum("extra_class", "class_i", "class_ii", name="pricing_grade"), nullable=False, unique=True)
    multiplier = Column(Numeric(5, 4), nullable=False, default=1.0)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    updated_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    editor = relationship("User", back_populates="pricing_edits", foreign_keys=[updated_by])

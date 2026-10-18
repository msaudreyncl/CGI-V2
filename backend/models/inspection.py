"""models/inspection.py — Inspection ORM model."""

import enum
from sqlalchemy import Column, Integer, String, Numeric, Boolean, DateTime, Text, Enum as SAEnum, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base


class GradeEnum(str, enum.Enum):
    extra_class = "extra_class"
    class_i     = "class_i"
    class_ii    = "class_ii"


class Inspection(Base):
    __tablename__ = "inspections"

    id                    = Column(Integer, primary_key=True, autoincrement=True)
    farmer_id             = Column(Integer, ForeignKey("farmers.id"), nullable=False, index=True)
    officer_id            = Column(Integer, ForeignKey("users.id"),   nullable=False, index=True)
    sample_weight_g       = Column(Numeric(7, 2),  nullable=False)
    total_beans_detected  = Column(Integer, nullable=False, default=0)
    image_path            = Column(String(500), nullable=False)
    # --- dual-view additions ---
    image_path_b          = Column(String(500), nullable=True,
                                   comment="Relative path to raw View B image")
    image_path_annotated_a = Column(String(500), nullable=True,
                                    comment="Relative path to YOLOv8-annotated View A image")
    image_path_annotated_b = Column(String(500), nullable=True,
                                    comment="Relative path to YOLOv8-annotated View B image")
    grade                 = Column(SAEnum(GradeEnum), nullable=False)
    over_threshold_flag   = Column(Boolean, nullable=False, default=False)
    notes                 = Column(Text, nullable=True)
    # transaction number carried forward from pending_transactions at analysis time
    txn_number            = Column(String(20), nullable=True, unique=True,
                                   comment="CGI-YYYYMMDD-XXXXXX from pending_transactions")
    created_at            = Column(DateTime, nullable=False, server_default=func.now())

    # Relationships
    farmer         = relationship("Farmer",       back_populates="inspections")
    officer        = relationship("User",         back_populates="inspections",    foreign_keys=[officer_id])
    defect_results = relationship("DefectResult", back_populates="inspection",     cascade="all, delete-orphan")
    transaction    = relationship("Transaction",  back_populates="inspection",     uselist=False)

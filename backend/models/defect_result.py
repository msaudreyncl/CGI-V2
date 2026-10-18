"""models/defect_result.py — DefectResult ORM model."""

import enum
from sqlalchemy import Column, Integer, Numeric, Boolean, Enum as SAEnum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base


class DefectType(str, enum.Enum):
    black_bean     = "black_bean"
    moldy_infested = "moldy_infested"
    immature       = "immature"
    broken         = "broken"
    dried_cherry   = "dried_cherry"
    foreign_matter = "foreign_matter"


class DefectResult(Base):
    __tablename__ = "defect_results"
    __table_args__ = (
        UniqueConstraint("inspection_id", "defect_type", name="uq_inspection_defect"),
    )

    id                = Column(Integer, primary_key=True, autoincrement=True)
    inspection_id     = Column(Integer, ForeignKey("inspections.id", ondelete="CASCADE"), nullable=False, index=True)
    defect_type       = Column(SAEnum(DefectType), nullable=False)
    bean_count        = Column(Integer,        nullable=False, default=0)
    defect_percentage = Column(Numeric(6, 3),  nullable=False, default=0)
    assigned_class    = Column(SAEnum("extra_class", "class_i", "class_ii", name="defect_assigned_class"), nullable=False)
    over_threshold    = Column(Boolean, nullable=False, default=False)

    inspection = relationship("Inspection", back_populates="defect_results")

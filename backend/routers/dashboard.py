"""routers/dashboard.py — Dashboard summary endpoint."""

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from database import get_db
from models.user import User, UserRole
from models.inspection import Inspection, GradeEnum
from models.transaction import Transaction
from schemas.inspection import InspectionListItem
from schemas.pricing import DashboardSummary
from auth import require_role

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def get_summary(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.officer)),
):
    now   = datetime.now(timezone.utc)
    today = now.date()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Totals
    total_today = (
        db.query(func.count(Inspection.id))
        .filter(func.date(Inspection.created_at) == today)
        .scalar() or 0
    )
    total_month = (
        db.query(func.count(Inspection.id))
        .filter(Inspection.created_at >= month_start)
        .scalar() or 0
    )

    # Grade distribution (all time)
    grade_dist = {g.value: 0 for g in GradeEnum}
    rows = db.query(Inspection.grade, func.count(Inspection.id)).group_by(Inspection.grade).all()
    for grade, count in rows:
        grade_dist[grade.value] = count

    # Average price per grade this month
    avg_price: dict = {}
    price_rows = (
        db.query(Inspection.grade, func.avg(Transaction.price_per_kg))
        .join(Transaction, Transaction.inspection_id == Inspection.id)
        .filter(Inspection.created_at >= month_start)
        .group_by(Inspection.grade)
        .all()
    )
    for grade, avg in price_rows:
        avg_price[grade.value] = round(float(avg), 2) if avg else 0.0

    # Total weight this month
    total_weight = (
        db.query(func.coalesce(func.sum(Transaction.weight_kg), 0))
        .join(Inspection, Inspection.id == Transaction.inspection_id)
        .filter(Inspection.created_at >= month_start)
        .scalar() or 0.0
    )

    # Recent inspections
    recent = (
        db.query(Inspection)
        .order_by(Inspection.created_at.desc())
        .limit(5)
        .all()
    )

    return DashboardSummary(
        total_inspections_today=total_today,
        total_inspections_month=total_month,
        grade_distribution=grade_dist,
        average_price_per_grade=avg_price,
        total_weight_kg_month=float(total_weight),
        recent_inspections=[InspectionListItem.model_validate(i).model_dump() for i in recent],
    )

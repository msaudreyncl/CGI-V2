"""
services/csv_export.py — Transaction history CSV exporter.
"""

from __future__ import annotations
import csv
import io

from sqlalchemy.orm import Session
from models.transaction import Transaction
from models.inspection import Inspection
from models.user import User, UserRole


def generate_transactions_csv(db: Session, current_user: User) -> bytes:
    """
    Generate a CSV file of transaction records.
    Admin/Officer: all transactions.
    Farmer: own transactions only (handled by router, always admin/officer here).
    """
    q = (
        db.query(Transaction)
        .join(Inspection, Inspection.id == Transaction.inspection_id)
        .order_by(Transaction.created_at.desc())
    )
    transactions = q.all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "Transaction ID", "Inspection ID", "Farmer ID", "Grade",
        "Weight (kg)", "Price/kg (PHP)", "Total Price (PHP)",
        "Currency", "Price Source", "Notes", "Date",
    ])
    for txn in transactions:
        inspection = db.get(Inspection, txn.inspection_id)
        writer.writerow([
            txn.id,
            txn.inspection_id,
            inspection.farmer_id if inspection else "",
            inspection.grade.value.replace("_", " ").title() if inspection else "",
            f"{float(txn.weight_kg):.4f}",
            f"{float(txn.price_per_kg):.4f}",
            f"{float(txn.total_price):.4f}",
            txn.currency,
            txn.price_source.value,
            txn.notes or "",
            txn.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        ])

    return buf.getvalue().encode("utf-8-sig")  # utf-8-sig for Excel compatibility

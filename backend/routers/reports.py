"""routers/reports.py — PDF, CSV export, and thermal print endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import get_db
from models.user import User, UserRole
from models.inspection import Inspection
from models.transaction import Transaction
from models.transaction import PrintStatus
from auth import get_current_user, require_role
from services.pdf_report import generate_inspection_pdf
from services.csv_export import generate_transactions_csv
from services.thermal_print import print_receipt

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/inspection/{inspection_id}/pdf")
def download_inspection_pdf(
    inspection_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    inspection = db.get(Inspection, inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found.")
    if (
        current_user.role == UserRole.farmer
        and current_user.farmer_profile
        and inspection.farmer_id != current_user.farmer_profile.id
    ):
        raise HTTPException(status_code=403, detail="Access denied.")

    pdf_bytes = generate_inspection_pdf(inspection)
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="inspection_{inspection_id}.pdf"'},
    )


@router.get("/transactions/csv")
def download_transactions_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.officer)),
):
    csv_bytes = generate_transactions_csv(db, current_user)
    return StreamingResponse(
        iter([csv_bytes]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="transactions.csv"'},
    )


@router.post("/transaction/{txn_id}/print")
def print_transaction_receipt(
    txn_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(UserRole.admin, UserRole.officer)),
):
    """
    Send an ESC/POS receipt to the thermal printer.

    Always returns HTTP 200 with {"status": "printed"|"failed", ...} so the
    frontend can offer a retry without a page reload or error crash.
    print_status is persisted to the Transaction row in both cases.
    """
    txn = db.get(Transaction, txn_id)
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found.")

    try:
        print_receipt(txn, db)
        txn.print_status = PrintStatus.printed
        db.commit()
        return {"status": "printed", "transaction_id": txn_id, "detail": None}
    except Exception as exc:
        txn.print_status = PrintStatus.failed
        db.commit()
        return {"status": "failed", "transaction_id": txn_id, "detail": str(exc)}

"""
services/thermal_print.py — ESC/POS thermal receipt printer.
"""

from __future__ import annotations
from sqlalchemy.orm import Session

from config import get_settings
from models.transaction import Transaction
from models.inspection import Inspection
from models.farmer import Farmer
from models.user import User

settings = get_settings()


def print_receipt(txn: Transaction, db: Session) -> None:
    """
    Print an ESC/POS receipt for the given transaction.
    Printer type (network/usb) is determined from settings.
    """
    inspection: Inspection = db.get(Inspection, txn.inspection_id)
    farmer: Farmer         = db.get(Farmer, inspection.farmer_id) if inspection else None
    farmer_user: User      = db.get(User, farmer.user_id) if farmer else None
    officer: User          = db.get(User, inspection.officer_id) if inspection else None

    grade_label = inspection.grade.value.replace("_", " ").title() if inspection else "N/A"
    farmer_name = farmer_user.name.strip() if farmer_user and farmer_user.name.strip() else "Not Available"
    officer_name = officer.name if officer else "N/A"

    try:
        from escpos.printer import Network, Usb
    except ImportError:
        raise RuntimeError("python-escpos is not installed. Run: pip install python-escpos")

    if settings.THERMAL_PRINTER_TYPE == "network":
        printer = Network(settings.THERMAL_PRINTER_HOST, settings.THERMAL_PRINTER_PORT)
    else:
        vid = int(settings.THERMAL_PRINTER_USB_VID, 16)
        pid = int(settings.THERMAL_PRINTER_USB_PID, 16)
        printer = Usb(vid, pid)

    try:
        printer.set(align="center", bold=True, width=2, height=2)
        printer.text("CGI\n")
        printer.set(align="center", bold=False, width=1, height=1)
        printer.text("Coffee Grade Identification\n")
        printer.text("-" * 32 + "\n")

        printer.set(align="left")
        printer.text(f"Transaction ID: {inspection.txn_number or 'N/A'}\n")
        printer.text(f"Farmer Name: {farmer_name}\n")
        # ASCII separator retains compatibility with existing thermal code pages.
        printer.text(f"Date & Time: {txn.created_at.strftime('%B %d, %Y - %I:%M %p')}\n")
        printer.text(f"Officer : {officer_name}\n")
        printer.text(f"Insp ID : {inspection.id}\n")
        printer.text("-" * 32 + "\n")

        printer.set(bold=True)
        printer.text(f"Grade   : {grade_label}\n")
        if inspection.over_threshold_flag:
            printer.text("! LOW VALUE - OVER THRESHOLD !\n")
        printer.set(bold=False)

        printer.text(f"Weight  : {float(txn.weight_kg):.3f} kg\n")
        printer.text(f"Price/kg: {txn.currency} {float(txn.price_per_kg):.2f}\n")
        printer.text("-" * 32 + "\n")

        printer.set(bold=True, width=1, height=2)
        printer.text(f"TOTAL   : {txn.currency} {float(txn.total_price):.2f}\n")
        printer.set(bold=False, width=1, height=1)

        printer.text("-" * 32 + "\n")
        printer.set(align="center")
        printer.text("Thank you!\n")
        printer.text("CGI System v1.0\n")
        printer.ln(3)
        printer.cut()
    finally:
        try:
            printer.close()
        except Exception:
            pass

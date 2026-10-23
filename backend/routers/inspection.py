"""routers/inspection.py — Inspection capture and listing endpoints."""

import base64
import math
import os
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config import get_settings
from database import get_db
from models.user import User, UserRole
from models.farmer import Farmer
from models.inspection import Inspection
from models.transaction import Transaction, TransactionStatus, PrintStatus, PriceSource
from models.pending_transaction import PendingTransaction, PendingStatus
from schemas.inspection import (
    InspectionOut, InspectionListItem, CapturePayload,
    DualCapturePayload, DualInspectionOut, AnalysisBypassOut,
)
from auth import get_current_user, require_role
from services.detection import run_detection, run_detection_with_annotation
from services.grading import evaluate_grade

router   = APIRouter(prefix="/api/inspection", tags=["inspection"])
settings = get_settings()


@router.post("/capture", response_model=InspectionOut, status_code=status.HTTP_201_CREATED)
def capture_and_analyze(
    body: CapturePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Accepts image (base64) + weight from the Pi node, runs YOLOv8 detection,
    applies grading, persists results, and returns the full inspection record.
    """
    # 1. Validate weight range
    if not (settings.WEIGHT_MIN_G <= body.weight_g <= settings.WEIGHT_MAX_G):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Sample weight {body.weight_g:.1f} g is outside the accepted range "
                f"({settings.WEIGHT_MIN_G:.0f}–{settings.WEIGHT_MAX_G:.0f} g). "
                "Adjust the sample weight and try again."
            ),
        )

    # 2. Validate farmer exists
    farmer = db.get(Farmer, body.farmer_id)
    if not farmer:
        raise HTTPException(status_code=404, detail="Farmer not found.")

    # 3. Decode and save image
    try:
        image_bytes = base64.b64decode(body.image_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image data.")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    filename   = f"{uuid.uuid4().hex}.jpg"
    image_path = os.path.join(settings.UPLOAD_DIR, filename)
    with open(image_path, "wb") as f:
        f.write(image_bytes)
    relative_path = f"static/uploads/{filename}"

    # 4. Run YOLOv8 detection
    detection_result = run_detection(image_path)

    # 5. Apply grading rules
    grading_result = evaluate_grade(detection_result)

    # 6. Determine officer: Pi node posts as the authenticated user (officer role)
    officer_id = current_user.id

    # 7. Persist inspection
    inspection = Inspection(
        farmer_id=body.farmer_id,
        officer_id=officer_id,
        sample_weight_g=body.weight_g,
        total_beans_detected=grading_result["total_beans"],
        image_path=relative_path,
        grade=grading_result["grade"],
        over_threshold_flag=grading_result["over_threshold_flag"],
    )
    db.add(inspection)
    db.flush()  # get inspection.id before adding defect rows

    # 8. Persist defect results
    from models.defect_result import DefectResult
    for dr in grading_result["defect_breakdown"]:
        db.add(DefectResult(
            inspection_id=inspection.id,
            defect_type=dr["defect_type"],
            bean_count=dr["count"],
            defect_percentage=dr["percentage"],
            assigned_class=dr["assigned_class"],
            over_threshold=dr["over_threshold"],
        ))

    db.commit()
    db.refresh(inspection)
    return InspectionOut.model_validate(inspection)


@router.get("", response_model=List[InspectionListItem])
def list_inspections(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Inspection)
    if current_user.role == UserRole.farmer:
        if not current_user.farmer_profile:
            return []
        q = q.filter(Inspection.farmer_id == current_user.farmer_profile.id)
    items = q.order_by(Inspection.created_at.desc()).offset(skip).limit(limit).all()
    return [InspectionListItem.model_validate(i) for i in items]


@router.get("/{inspection_id}", response_model=InspectionOut)
def get_inspection(
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
    return InspectionOut.model_validate(inspection)


@router.post("/capture-dual", response_model=DualInspectionOut | AnalysisBypassOut,
             status_code=status.HTTP_201_CREATED)
async def capture_dual_and_analyze(
    body: DualCapturePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.admin, UserRole.officer)),
):
    """
    Stage 4 — Analyze: accept View A and View B images, run YOLOv8 on each,
    produce annotated images, reconcile counts (two-view average), apply
    ASEAN grading, calculate suggested price, and persist all records atomically.

    Weight is read from the pending_transactions row (already validated in Stage 2).
    txn_number, farmer_id, and created_at are carried forward from pending_transactions.

    Two-view reconciliation: average of both views as per spec §4.2.
      total_beans = round((total_A + total_B) / 2)
      per defect : reconciled_count = round((count_A + count_B) / 2)
    """
    from services.pricing import suggest_price

    # 1. Validate pending transaction
    pending = db.get(PendingTransaction, body.pending_id)
    if not pending:
        raise HTTPException(status_code=404, detail="Pending transaction not found.")
    if pending.weight_g is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Weight has not been recorded for this transaction. Complete Stage 2 first.",
        )

    weight_g = float(pending.weight_g)

    # 2. Decode and save both raw images
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    uid         = uuid.uuid4().hex
    path_a_raw  = os.path.join(settings.UPLOAD_DIR, f"{uid}_a.jpg")
    path_b_raw  = os.path.join(settings.UPLOAD_DIR, f"{uid}_b.jpg")
    path_a_ann  = os.path.join(settings.UPLOAD_DIR, f"{uid}_a_annotated.jpg")
    path_b_ann  = os.path.join(settings.UPLOAD_DIR, f"{uid}_b_annotated.jpg")

    # Collect paths for rollback on failure
    created_files = []

    try:
        for b64_str, save_path in (
            (body.image_a_b64, path_a_raw),
            (body.image_b_b64, path_b_raw),
        ):
            try:
                img_bytes = base64.b64decode(b64_str)
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid base64 image data.")
            with open(save_path, "wb") as f:
                f.write(img_bytes)
            created_files.append(save_path)

        # Temporary capture-only workflow: no synthetic counts, grade or pricing.
        # Do not hide inference errors when a model file is present.
        if settings.YOLO_ALLOW_MISSING_MODEL and not os.path.exists(settings.YOLO_MODEL_PATH):
            pending.status = PendingStatus.captured
            db.commit()
            return AnalysisBypassOut(
                message="Analysis skipped — trained YOLOv8 model unavailable. No grade or price was generated.",
                pending_id=pending.id, txn_number=pending.txn_number,
                created_at=pending.created_at, sample_weight_g=weight_g,
                image_path=f"static/uploads/{uid}_a.jpg",
                image_path_b=f"static/uploads/{uid}_b.jpg",
            )

        # 3. Run YOLOv8 with annotation on both images
        det_a, ann_bytes_a = run_detection_with_annotation(path_a_raw)
        det_b, ann_bytes_b = run_detection_with_annotation(path_b_raw)

        # Save annotated images
        if ann_bytes_a:
            with open(path_a_ann, "wb") as f:
                f.write(ann_bytes_a)
            created_files.append(path_a_ann)

        if ann_bytes_b:
            with open(path_b_ann, "wb") as f:
                f.write(ann_bytes_b)
            created_files.append(path_b_ann)

        # 4. Two-view reconciliation (spec §4.2): average both views
        total_beans = math.floor((det_a["total_beans"] + det_b["total_beans"]) / 2 + 0.5)

        all_defect_types = set(det_a["class_counts"]) | set(det_b["class_counts"])
        reconciled_counts = {}
        for dt in all_defect_types:
            c_a = det_a["class_counts"].get(dt, 0)
            c_b = det_b["class_counts"].get(dt, 0)
            reconciled_counts[dt] = math.floor((c_a + c_b) / 2 + 0.5)

        reconciled_detection = {
            "total_beans":  total_beans,
            "class_counts": reconciled_counts,
        }

        # 5. Apply ASEAN grading on reconciled counts
        grading_result = evaluate_grade(reconciled_detection)

        # 6. Relative paths for DB storage
        rel_a_raw = f"static/uploads/{uid}_a.jpg"
        rel_b_raw = f"static/uploads/{uid}_b.jpg"
        rel_a_ann = f"static/uploads/{uid}_a_annotated.jpg" if ann_bytes_a else None
        rel_b_ann = f"static/uploads/{uid}_b_annotated.jpg" if ann_bytes_b else None

        # 7. Persist Inspection row, carrying forward pending transaction data
        inspection = Inspection(
            farmer_id             = pending.farmer_id,
            officer_id            = current_user.id,
            sample_weight_g       = weight_g,
            total_beans_detected  = grading_result["total_beans"],
            image_path            = rel_a_raw,
            image_path_b          = rel_b_raw,
            image_path_annotated_a = rel_a_ann,
            image_path_annotated_b = rel_b_ann,
            grade                 = grading_result["grade"],
            over_threshold_flag   = grading_result["over_threshold_flag"],
            txn_number            = pending.txn_number,
            created_at            = pending.created_at,   # preserve original timestamp
        )
        db.add(inspection)
        db.flush()  # get inspection.id

        # 8. Persist DefectResult rows
        from models.defect_result import DefectResult
        for dr in grading_result["defect_breakdown"]:
            db.add(DefectResult(
                inspection_id     = inspection.id,
                defect_type       = dr["defect_type"],
                bean_count        = dr["count"],
                defect_percentage = dr["percentage"],
                assigned_class    = dr["assigned_class"],
                over_threshold    = dr["over_threshold"],
            ))

        # 9. Fetch suggested price (async service, uses existing pricing engine)
        pricing = await suggest_price(inspection, db)

        # 10. Create finalized Transaction row
        total_price = round(pricing["price_per_kg"] * (weight_g / 1000.0), 4)
        txn = Transaction(
            inspection_id = inspection.id,
            weight_kg     = round(weight_g / 1000.0, 4),
            price_per_kg  = pricing["price_per_kg"],
            total_price   = total_price,
            currency      = pricing["currency"],
            price_source  = PriceSource.api if pricing["source"] != "manual" else PriceSource.manual,
            status        = TransactionStatus.analyzed,
            print_status  = PrintStatus.pending,
        )
        db.add(txn)

        # 11. Update pending transaction status
        pending.status = PendingStatus.analyzed
        db.commit()
        db.refresh(inspection)
        db.refresh(txn)

    except HTTPException:
        # Clean up any files written before the error
        for fp in created_files:
            try:
                os.remove(fp)
            except OSError:
                pass
        db.rollback()
        raise
    except Exception as exc:
        for fp in created_files:
            try:
                os.remove(fp)
            except OSError:
                pass
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {exc}",
        )

    # 12. Build extended response
    insp_out = InspectionOut.model_validate(inspection)
    return DualInspectionOut(
        **insp_out.model_dump(),
        txn_id             = txn.id,
        price_per_kg       = pricing["price_per_kg"],
        market_rate_per_kg = pricing["market_rate_per_kg"],
        multiplier         = pricing["multiplier"],
        total_price        = float(txn.total_price),
        currency           = pricing["currency"],
        price_source       = pricing["source"],
    )

"""
services/detection.py — YOLOv8 detection engine.

Loads the trained model once at startup and returns per-class bean counts
from a given image path.
"""

from __future__ import annotations
import os
from typing import Dict, Tuple

from config import get_settings

settings = get_settings()

# YOLO class ID → defect type name (must match training labels)
CLASS_ID_MAP: Dict[int, str] = {
    0: "black_bean",
    1: "moldy_infested",
    2: "immature",
    3: "broken",
    4: "dried_cherry",
    5: "foreign_matter",
}

_model = None  # Lazy-loaded singleton


def _get_model():
    global _model
    if _model is not None:
        return _model

    model_path = settings.YOLO_MODEL_PATH
    if not os.path.exists(model_path):
        raise FileNotFoundError(
            f"YOLOv8 model not found at '{model_path}'. "
            "Place the trained .pt file there or update YOLO_MODEL_PATH in .env"
        )

    from ultralytics import YOLO
    _model = YOLO(model_path)
    return _model


def run_detection(image_path: str) -> Dict:
    """
    Run YOLOv8 inference on the given image.

    Returns:
        {
            "total_beans": int,
            "class_counts": {"black_bean": n, "moldy_infested": n, ...}
        }
    """
    model   = _get_model()
    results = model.predict(
        source=image_path,
        conf=settings.YOLO_CONFIDENCE,
        verbose=False,
        save=False,
    )

    class_counts: Dict[str, int] = {name: 0 for name in CLASS_ID_MAP.values()}

    for result in results:
        if result.boxes is None:
            continue
        for cls_tensor in result.boxes.cls:
            cls_id = int(cls_tensor.item())
            defect_name = CLASS_ID_MAP.get(cls_id)
            if defect_name:
                class_counts[defect_name] += 1

    total_beans = sum(class_counts.values())
    return {"total_beans": total_beans, "class_counts": class_counts}


def run_detection_with_annotation(image_path: str) -> Tuple[Dict, bytes]:
    """
    Run YOLOv8 inference and also produce an annotated image.

    Identical to run_detection() for the detection result, but additionally
    returns JPEG bytes of the image with bounding boxes, defect labels, and
    confidence scores drawn by YOLOv8's result.plot().

    Returns:
        (detection_result, annotated_jpeg_bytes)
        detection_result — same dict as run_detection()
        annotated_jpeg_bytes — JPEG-encoded annotated image bytes
    """
    model   = _get_model()
    results = model.predict(
        source=image_path,
        conf=settings.YOLO_CONFIDENCE,
        verbose=False,
        save=False,
    )

    class_counts: Dict[str, int] = {name: 0 for name in CLASS_ID_MAP.values()}

    for result in results:
        if result.boxes is None:
            continue
        for cls_tensor in result.boxes.cls:
            cls_id = int(cls_tensor.item())
            defect_name = CLASS_ID_MAP.get(cls_id)
            if defect_name:
                class_counts[defect_name] += 1

    total_beans = sum(class_counts.values())
    detection_result = {"total_beans": total_beans, "class_counts": class_counts}

    # Generate annotated image using YOLOv8's built-in plot() method.
    # result.plot() returns a NumPy BGR array; encode to JPEG bytes.
    annotated_bytes = b""
    if results:
        annotated_bgr = results[0].plot()   # NumPy array (H, W, 3), BGR
        try:
            import cv2
            ok, buf = cv2.imencode(".jpg", annotated_bgr)
            if ok:
                annotated_bytes = buf.tobytes()
        except ImportError:
            # Fallback: use PIL if cv2 is unavailable
            from PIL import Image
            import io
            # plot() returns BGR; convert to RGB for PIL
            annotated_rgb = annotated_bgr[:, :, ::-1]
            img = Image.fromarray(annotated_rgb)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=90)
            annotated_bytes = buf.getvalue()

    return detection_result, annotated_bytes

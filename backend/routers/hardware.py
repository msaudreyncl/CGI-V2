"""routers/hardware.py — Hardware status, weight poll, and camera capture proxy.

Acts as a single-origin proxy so the browser only communicates with the
FastAPI backend (port 8000).  All three endpoints forward calls to the Pi
node HTTP server (pi_server.py, default port 5000).

Hardware gate rules (per spec §1.3 confirmed design):
  - Camera + Scale: must be "ready" before the officer can proceed past Prepare.
  - Printer: non-blocking — returns "ready" or "warning" (never "error").
"""

import asyncio
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status

import httpx

from config import get_settings
from models.user import User, UserRole
from auth import require_role

router   = APIRouter(prefix="/api/hardware", tags=["hardware"])
settings = get_settings()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _pi_get(path: str) -> dict:
    """GET {PI_NODE_URL}{path} and return parsed JSON, or raise on failure."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(settings.PI_NODE_URL.rstrip("/") + path)
        # /weight reports independent readiness even when the scale failed.
        if path == "/weight" and resp.status_code == 503:
            data = resp.json()
            if data.get("scale") == "error":
                return data
        resp.raise_for_status()
        return resp.json()


async def _pi_post(path: str, body: dict) -> dict:
    """POST {PI_NODE_URL}{path} with JSON body, return parsed JSON."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            settings.PI_NODE_URL.rstrip("/") + path,
            json=body,
        )
        resp.raise_for_status()
        return resp.json()


async def _check_printer() -> str:
    """
    Attempt a TCP connection to the configured thermal printer.
    Returns "ready" on success, "warning" on failure (non-blocking per design).
    """
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(
                settings.THERMAL_PRINTER_HOST,
                settings.THERMAL_PRINTER_PORT,
            ),
            timeout=3.0,
        )
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return "ready"
    except Exception:
        return "warning"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status")
async def hardware_status(
    _: User = Depends(require_role(UserRole.admin, UserRole.officer)),
):
    """
    Check the readiness of all three hardware components.

    Returns:
        camera:  "ready" | "error"
        scale:   "ready" | "error"
        printer: "ready" | "warning"   (printer failure is non-blocking)
    """
    data = {}
    try:
        data = await _pi_get("/weight")
        camera_status = data.get("camera", "error")
        scale_status = data.get("scale", "error")
    except Exception:
        camera_status = scale_status = "error"

    printer_status = await _check_printer()

    return {
        "camera":  camera_status,
        "scale":   scale_status,
        "printer": printer_status,
        "simulated": data.get("simulated", False),
    }


@router.get("/weight")
async def get_weight(
    _: User = Depends(require_role(UserRole.admin, UserRole.officer)),
):
    """
    Proxy a live weight reading from the Pi node.

    Returns:
        weight_g  — current reading in grams
        stable    — True when consecutive readings differ by ≤ 0.5 g
        in_range  — True when 340 ≤ weight_g ≤ 360
    """
    try:
        data = await _pi_get("/weight")
        if data.get("scale") == "error":
            raise HTTPException(status_code=503, detail=data.get("error", "Scale unavailable"))
        return data
    except HTTPException:
        raise
    except httpx.ConnectError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pi node is unreachable. Ensure pi_server.py is running.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Pi node error: {exc}",
        )


class HardwareCaptureRequest(BaseModel):
    view: str  # "A" or "B"


@router.post("/capture")
async def trigger_capture(
    body: HardwareCaptureRequest,
    _: User = Depends(require_role(UserRole.admin, UserRole.officer)),
):
    """
    Trigger the Pi camera and return the captured image as base64 JPEG.

    Request body:
        view — "A" or "B"

    Returns:
        image_b64 — base64-encoded JPEG bytes
        view      — echoed back ("A" or "B")
    """
    view = body.view.upper()
    if view not in ("A", "B"):
        raise HTTPException(status_code=400, detail="view must be 'A' or 'B'")

    try:
        return await _pi_post("/capture", {"view": view})
    except httpx.ConnectError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Pi node is unreachable. Ensure pi_server.py is running.",
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Pi node returned error {exc.response.status_code}: {exc.response.text}",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Pi node error: {exc}",
        )


class HardwareWeightAction(BaseModel):
    action: str


@router.post("/weight")
async def tare_weight(
    body: HardwareWeightAction,
    _: User = Depends(require_role(UserRole.admin, UserRole.officer)),
):
    """Tare the empty platform using the existing weight resource."""
    if body.action != "tare":
        raise HTTPException(status_code=400, detail="action must be tare")
    try:
        return await _pi_post("/weight", {"action": "tare"})
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Scale tare failed: {exc}")

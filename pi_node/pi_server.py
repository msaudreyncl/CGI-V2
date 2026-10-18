"""
pi_server.py — CGI Pi Node HTTP Server

A lightweight stdlib HTTP server that exposes two endpoints so the FastAPI
backend can poll the live weight reading and trigger camera captures on demand.

Run this alongside sensor_node.py (separate terminal or systemd unit):

    python pi_server.py

Endpoints:
    GET  /weight   → {"weight_g": float, "stable": bool, "in_range": bool}
    POST /capture  → body: {"view": "A"|"B"}
                   → {"image_b64": "<base64 jpeg>"}

On non-Pi machines both endpoints return safe simulated values so the rest
of the workflow can be developed and tested without physical hardware.
"""

import base64
import configparser
import io
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

# ── Detect Pi hardware ────────────────────────────────────────────────────────
try:
    from hx711_reader import (
        _ON_PI as _HX711_AVAILABLE,
        _load_config,
        _build_hx711,
        read_weight_g,
        is_weight_in_range,
    )
    from camera_capture import _ON_PI as _CAMERA_AVAILABLE, capture_image
    _ON_PI = _HX711_AVAILABLE and _CAMERA_AVAILABLE
except (ImportError, RuntimeError, FileNotFoundError):
    _ON_PI = False

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.ini")

# ── Module-level state for stability detection ────────────────────────────────
_hx            = None          # HX711 instance (Pi only)
_cfg           = None          # ConfigParser instance
_last_weight   = None          # Previous reading for stability comparison
_stability_lock = threading.Lock()

STABILITY_THRESHOLD_G = 0.5   # readings within ±0.5 g are considered stable


def _get_cfg() -> configparser.ConfigParser:
    global _cfg
    if _cfg is None:
        if _ON_PI:
            _cfg = _load_config()
        else:
            _cfg = configparser.ConfigParser()
    return _cfg


def _get_hx():
    global _hx
    if _hx is None and _ON_PI:
        _hx = _build_hx711(_get_cfg())
    return _hx


def _read_weight():
    """
    Read the current weight and determine stability.
    Returns (weight_g: float, stable: bool, in_range: bool).
    """
    global _last_weight

    if _ON_PI:
        hx = _get_hx()
        cfg = _get_cfg()
        weight_g = read_weight_g(hx, cfg)
        in_range = is_weight_in_range(weight_g, cfg)
    else:
        # Simulation mode — steady 350 g
        weight_g = 350.0
        in_range = True

    with _stability_lock:
        if _last_weight is None:
            stable = False
        else:
            stable = abs(weight_g - _last_weight) <= STABILITY_THRESHOLD_G
        _last_weight = weight_g

    return weight_g, stable, in_range


def _capture_image_b64() -> str:
    """Capture an image and return it as a base64-encoded JPEG string."""
    if _ON_PI:
        image_bytes = capture_image()
    else:
        # Simulation mode — return a tiny white JPEG
        try:
            from PIL import Image
            img = Image.new("RGB", (1280, 960), color=(240, 230, 210))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            image_bytes = buf.getvalue()
        except ImportError:
            # Minimal valid 1×1 white JPEG (hard-coded bytes)
            image_bytes = (
                b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
                b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
                b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
                b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x1e"
                b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
                b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00"
                b"\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
                b"\xff\xc4\x00\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04"
                b"\x04\x00\x00\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa"
                b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfb\x00\xff\xd9"
            )
    return base64.b64encode(image_bytes).decode("utf-8")


# ── HTTP request handler ──────────────────────────────────────────────────────

class PiRequestHandler(BaseHTTPRequestHandler):
    """Minimal HTTP handler for weight polling and camera capture."""

    def log_message(self, format, *args):  # noqa: A002
        # Suppress default Apache-style access log; write to stdout only
        print(f"[pi_server] {self.address_string()} - {format % args}")

    def _send_json(self, status: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, status: int, detail: str):
        self._send_json(status, {"error": detail})

    def do_GET(self):
        if self.path == "/weight":
            try:
                weight_g, stable, in_range = _read_weight()
                self._send_json(200, {
                    "weight_g": round(weight_g, 2),
                    "stable":   stable,
                    "in_range": in_range,
                })
            except Exception as exc:
                self._send_error_json(500, str(exc))
        else:
            self._send_error_json(404, "Not found")

    def do_POST(self):
        if self.path == "/capture":
            length = int(self.headers.get("Content-Length", 0))
            raw    = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                self._send_error_json(400, "Invalid JSON body")
                return

            view = body.get("view", "A").upper()
            if view not in ("A", "B"):
                self._send_error_json(400, "view must be 'A' or 'B'")
                return

            try:
                image_b64 = _capture_image_b64()
                self._send_json(200, {"image_b64": image_b64, "view": view})
            except Exception as exc:
                self._send_error_json(500, str(exc))
        else:
            self._send_error_json(404, "Not found")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    cfg = _get_cfg()
    host = cfg.get("server", "PI_SERVER_HOST", fallback="0.0.0.0")
    port = cfg.getint("server", "PI_SERVER_PORT", fallback=5000)

    mode = "Pi hardware" if _ON_PI else "simulation (non-Pi)"
    print(f"=== CGI Pi Server ({mode}) ===")
    print(f"Listening on {host}:{port}")
    print("  GET  /weight   — live weight reading")
    print("  POST /capture  — trigger camera (body: {\"view\": \"A\"|\"B\"})")

    server = HTTPServer((host, port), PiRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Pi server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

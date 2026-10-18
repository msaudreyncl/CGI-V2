"""
camera_capture.py — Pi Camera Module 3 image capture using picamera2.

Captures a single still image and returns the JPEG bytes or saves to a file.
Falls back to a dummy PNG on non-Pi machines for development testing.
"""

import io
import os
import time
import configparser
from typing import Optional

try:
    from picamera2 import Picamera2
    _ON_PI = True
except (ImportError, RuntimeError):
    _ON_PI = False


def _load_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), "config.ini")
    if os.path.exists(config_path):
        cfg.read(config_path)
    return cfg


def capture_image(save_path: Optional[str] = None) -> bytes:
    """
    Capture a still image from the Pi Camera Module 3.

    Args:
        save_path: If provided, also saves the image to this file path.

    Returns:
        Raw JPEG bytes of the captured image.
    """
    cfg = _load_config()

    if not _ON_PI:
        # Development fallback — return a tiny 1x1 white JPEG
        from PIL import Image
        img = Image.new("RGB", (1280, 960), color=(240, 230, 210))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        data = buf.getvalue()
        if save_path:
            with open(save_path, "wb") as f:
                f.write(data)
        return data

    width  = cfg.getint("camera", "RESOLUTION_WIDTH",  fallback=1920)
    height = cfg.getint("camera", "RESOLUTION_HEIGHT", fallback=1080)
    af_wait = cfg.getfloat("camera", "AUTOFOCUS_WAIT", fallback=1.5)

    cam = Picamera2()
    try:
        still_config = cam.create_still_configuration(
            main={"size": (width, height), "format": "BGR888"}
        )
        cam.configure(still_config)
        cam.start()

        # Allow autofocus to settle
        time.sleep(af_wait)

        buf = io.BytesIO()
        cam.capture_file(buf, format="jpeg")
        data = buf.getvalue()

        if save_path:
            with open(save_path, "wb") as f:
                f.write(data)

        return data
    finally:
        cam.stop()
        cam.close()


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "test_capture.jpg"
    img_bytes = capture_image(save_path=out)
    print(f"Captured {len(img_bytes):,} bytes → {out}")

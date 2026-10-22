"""
camera_capture.py — Pi Camera Module 3 image capture using picamera2.

Captures a single still image and returns the JPEG bytes or saves to a file.
Uses a simulated JPEG only when the explicit hardware mode policy permits it.
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

    from hardware_runtime import simulated
    if simulated(cfg):
        # Development image — never used to mask hardware failures
        from PIL import Image
        img = Image.new("RGB", (1280, 960), color=(240, 230, 210))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        data = buf.getvalue()
        if save_path:
            with open(save_path, "wb") as f:
                f.write(data)
        return data

    if not _ON_PI:
        raise RuntimeError('Picamera2 unavailable; install the Raspberry Pi OS camera packages')

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
        if not cam.autofocus_cycle():
            raise RuntimeError('Camera autofocus failed; check lighting and sample distance')

        buf = io.BytesIO()
        cam.capture_file(buf, format="jpeg")
        data = buf.getvalue()

        if save_path:
            with open(save_path, "wb") as f:
                f.write(data)

        return data
    finally:
        cam.close()


def camera_ready():
    if not _ON_PI:
        raise RuntimeError('Picamera2 driver unavailable')
    cam = Picamera2()
    try:
        cam.configure(cam.create_still_configuration())
        cam.start()
        cam.capture_metadata()
        return True
    finally:
        cam.close()


if __name__ == "__main__":
    import sys
    out = sys.argv[1] if len(sys.argv) > 1 else "test_capture.jpg"
    from hardware_runtime import simulated, run_hardware
    if simulated(_load_config()):
        img_bytes = capture_image(save_path=out)
    else:
        img_bytes = run_hardware('capture', timeout=20)
        with open(out, 'wb') as stream:
            stream.write(img_bytes)
    print(f"Captured {len(img_bytes):,} bytes → {out}")

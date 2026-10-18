"""
sensor_node.py — CGI Raspberry Pi Sensor Node

Main entry point for the Pi sensor node.
Reads weight from HX711, captures image from Pi Camera Module 3,
and POSTs both to the CGI backend API.

Trigger modes:
  1. GPIO button press (configured in config.ini → gpio.TRIGGER_BUTTON_PIN)
  2. Manual ENTER key (interactive / testing mode)
  3. Single-shot with --once flag

Usage:
    python sensor_node.py           # Wait-loop mode (GPIO button or ENTER)
    python sensor_node.py --once    # Capture once and exit
    python sensor_node.py --tare    # Tare the scale and exit
"""

import argparse
import base64
import configparser
import json
import os
import sys
import time

import requests

try:
    import RPi.GPIO as GPIO
    _ON_PI = True
except (ImportError, RuntimeError):
    _ON_PI = False

from hx711_reader import _load_config, _build_hx711, tare, read_weight_g, is_weight_in_range
from camera_capture import capture_image

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.ini")


def _get_server_url(cfg: configparser.ConfigParser) -> str:
    return cfg.get("server", "SERVER_URL", fallback="http://localhost:8000")


def _get_token(cfg: configparser.ConfigParser) -> str:
    return cfg.get("server", "PI_NODE_TOKEN", fallback="")


def _setup_gpio(cfg: configparser.ConfigParser):
    """Configure GPIO trigger button if on a Pi."""
    if not _ON_PI:
        return None
    pin = cfg.getint("gpio", "TRIGGER_BUTTON_PIN", fallback=17)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    return pin


def _wait_for_trigger(button_pin):
    """Block until GPIO button press or ENTER key."""
    if _ON_PI and button_pin is not None:
        print("Ready. Press the trigger button (or ENTER) to capture...")
        while True:
            if GPIO.input(button_pin) == GPIO.LOW:
                time.sleep(0.05)  # debounce
                if GPIO.input(button_pin) == GPIO.LOW:
                    return
            # Also allow keyboard trigger
            import select
            r, _, _ = select.select([sys.stdin], [], [], 0.1)
            if r:
                sys.stdin.readline()
                return
    else:
        input("Press ENTER to capture...")


def do_capture(cfg: configparser.ConfigParser, hx=None) -> dict:
    """
    Perform one full capture cycle:
      1. Read weight (enforce 340-360 g)
      2. Capture image
      3. POST to backend

    Returns the backend response JSON dict, or raises on error.
    """
    server_url = _get_server_url(cfg)
    token      = _get_token(cfg)

    # --- 1. Read weight ---
    if _ON_PI and hx is not None:
        weight_g = read_weight_g(hx, cfg)
    else:
        # Simulation fallback
        weight_g = 350.0
        print("[SIMULATION] Using dummy weight: 350.0 g")

    print(f"Weight: {weight_g:.1f} g", end="  ")

    if not is_weight_in_range(weight_g, cfg):
        w_min = cfg.getfloat("load_cell", "WEIGHT_MIN_G", fallback=340)
        w_max = cfg.getfloat("load_cell", "WEIGHT_MAX_G", fallback=360)
        msg = (
            f"Weight {weight_g:.1f} g is outside the accepted range "
            f"({w_min:.0f}–{w_max:.0f} g). Adjust the sample and try again."
        )
        print(f"\n[WARNING] {msg}")
        return {"error": "weight_out_of_range", "detail": msg, "weight_g": weight_g}

    print("[OK]")

    # --- 2. Capture image ---
    print("Capturing image...", end=" ", flush=True)
    image_bytes = capture_image()
    image_b64   = base64.b64encode(image_bytes).decode("utf-8")
    print(f"{len(image_bytes):,} bytes captured.")

    # --- 3. POST to backend ---
    endpoint = f"{server_url.rstrip('/')}/api/inspection/capture"
    headers  = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload  = {"weight_g": weight_g, "image_b64": image_b64}

    print(f"Sending to {endpoint} ...", end=" ", flush=True)
    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        result = resp.json()
        print(f"Response: {resp.status_code} OK")
        return result
    except requests.exceptions.ConnectionError:
        print("\n[ERROR] Cannot reach backend. Check SERVER_URL in config.ini.")
        return {"error": "connection_error"}
    except requests.exceptions.HTTPError as e:
        print(f"\n[ERROR] Backend returned {resp.status_code}: {resp.text}")
        return {"error": "http_error", "detail": str(e)}


def main():
    parser = argparse.ArgumentParser(description="CGI Pi Sensor Node")
    parser.add_argument("--once",  action="store_true", help="Capture once and exit")
    parser.add_argument("--tare",  action="store_true", help="Tare the scale and exit")
    args = parser.parse_args()

    cfg = _load_config()

    # Tare only
    if args.tare:
        if not _ON_PI:
            print("Tare requires a real Pi with HX711 connected.")
            sys.exit(1)
        hx = _build_hx711(cfg)
        tare(hx, cfg.getint("load_cell", "READINGS_TO_AVERAGE", fallback=10))
        GPIO.cleanup()
        return

    # Set up hardware
    hx         = _build_hx711(cfg) if _ON_PI else None
    button_pin = _setup_gpio(cfg)

    print("=== CGI Pi Sensor Node ===")
    print(f"Backend: {_get_server_url(cfg)}")

    if args.once:
        result = do_capture(cfg, hx)
        print(json.dumps(result, indent=2))
    else:
        try:
            while True:
                _wait_for_trigger(button_pin)
                result = do_capture(cfg, hx)
                if "error" not in result:
                    print("\n--- Inspection submitted successfully ---")
                    grade = result.get("grade", "unknown").replace("_", " ").title()
                    over  = result.get("over_threshold_flag", False)
                    print(f"  Grade: {grade}" + (" ⚠ OVER THRESHOLD" if over else ""))
                    print(f"  Total beans detected: {result.get('total_beans_detected', 'N/A')}")
                print()
        except KeyboardInterrupt:
            print("\nShutting down.")
        finally:
            if _ON_PI:
                GPIO.cleanup()


if __name__ == "__main__":
    main()

"""
hx711_reader.py — HX711 load cell reader with tare and calibration support.

Usage:
    python hx711_reader.py              # Print current weight continuously
    python hx711_reader.py --tare       # Tare (zero) the scale
    python hx711_reader.py --calibrate  # Interactive calibration wizard
"""

import argparse
import configparser
import os
import sys
import time

try:
    import RPi.GPIO as GPIO
    from hx711 import HX711
    _ON_PI = True
except (ImportError, RuntimeError):
    # Allow import on non-Pi machines for testing
    _ON_PI = False

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.ini")


def _load_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(
            f"Config file not found: {CONFIG_PATH}\n"
            "Copy config.ini.example to config.ini and edit it first."
        )
    cfg.read(CONFIG_PATH)
    return cfg


def _build_hx711(cfg: configparser.ConfigParser):
    """Instantiate and configure the HX711."""
    dt_pin  = cfg.getint("load_cell", "HX711_DT_PIN")
    sck_pin = cfg.getint("load_cell", "HX711_SCK_PIN")
    hx = HX711(dout_pin=dt_pin, pd_sck_pin=sck_pin)
    hx.reset()
    return hx


def tare(hx, readings: int = 10) -> float:
    """Tare the scale and return the raw offset."""
    print("Taring — keep the scale empty...")
    time.sleep(1)
    hx.tare(times=readings)
    offset = hx.get_current_weight(readings)
    print(f"Tare complete. Offset reading: {offset:.2f}")
    return offset


def read_weight_g(hx, cfg: configparser.ConfigParser) -> float:
    """Return a stable weight reading in grams."""
    cal_factor   = cfg.getfloat("load_cell", "CALIBRATION_FACTOR")
    n_readings   = cfg.getint("load_cell",   "READINGS_TO_AVERAGE")
    raw = hx.get_current_weight(n_readings)
    return raw / cal_factor


def is_weight_in_range(weight_g: float, cfg: configparser.ConfigParser) -> bool:
    """Return True if weight is within the configured 340–360 g range."""
    w_min = cfg.getfloat("load_cell", "WEIGHT_MIN_G")
    w_max = cfg.getfloat("load_cell", "WEIGHT_MAX_G")
    return w_min <= weight_g <= w_max


def calibrate():
    """Interactive calibration wizard. Prints the calibration factor to use in config.ini."""
    cfg = _load_config()
    if not _ON_PI:
        print("Calibration requires a real Raspberry Pi with HX711 connected.")
        sys.exit(1)

    hx = _build_hx711(cfg)
    n  = cfg.getint("load_cell", "READINGS_TO_AVERAGE")

    print("=== HX711 Calibration Wizard ===")
    print("Step 1: Remove all weight from the scale.")
    input("Press ENTER when ready...")
    hx.tare(times=n)
    print("Tare set.\n")

    known_weight = float(input("Step 2: Place a known weight (in grams) on the scale.\nEnter the known weight in grams: "))
    input("Place the weight now, then press ENTER...")
    time.sleep(0.5)

    raw = hx.get_current_weight(n)
    if raw == 0:
        print("ERROR: Raw reading is 0. Check wiring.")
        sys.exit(1)

    cal_factor = raw / known_weight
    print(f"\nCalibration factor: {cal_factor:.6f}")
    print(f"Update CALIBRATION_FACTOR = {cal_factor:.6f} in config.ini")

    GPIO.cleanup()


def main():
    parser = argparse.ArgumentParser(description="HX711 weight reader")
    parser.add_argument("--tare",      action="store_true", help="Tare the scale")
    parser.add_argument("--calibrate", action="store_true", help="Run calibration wizard")
    args = parser.parse_args()

    if args.calibrate:
        calibrate()
        return

    if not _ON_PI:
        print("[SIMULATION] Not running on a Pi — returning dummy weight of 350.0 g")
        return 350.0

    cfg = _load_config()
    hx  = _build_hx711(cfg)

    if args.tare:
        tare(hx, cfg.getint("load_cell", "READINGS_TO_AVERAGE"))
        GPIO.cleanup()
        return

    print("Reading weight continuously (Ctrl+C to stop)...")
    try:
        while True:
            weight = read_weight_g(hx, cfg)
            in_range = is_weight_in_range(weight, cfg)
            status = "OK" if in_range else "OUT OF RANGE"
            print(f"Weight: {weight:.1f} g  [{status}]")
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()


if __name__ == "__main__":
    main()

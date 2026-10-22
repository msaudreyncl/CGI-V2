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
import math
import statistics
import tempfile

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


def raw_mean(hx, readings=10):
    # hx711==1.1.2.3 exposes raw samples, not tare/get_current_weight.
    values = hx.get_raw_data(times=readings)
    if not values or len(values) != readings or any(
        isinstance(v, bool) or not math.isfinite(v) or v in (-8388608, 8388607)
        for v in values
    ):
        raise RuntimeError("Invalid HX711 readings; check wiring")
    return statistics.mean(values)


def save_scale_config(cfg):
    # Atomic replacement avoids partially written calibration after power loss.
    fd, path = tempfile.mkstemp(dir=os.path.dirname(CONFIG_PATH), prefix='.scale-')
    try:
        with os.fdopen(fd, 'w') as stream:
            cfg.write(stream)
        os.replace(path, CONFIG_PATH)
    finally:
        if os.path.exists(path):
            os.unlink(path)


def tare(hx, readings=10):
    cfg = _load_config()
    offset = raw_mean(hx, readings)
    cfg.set('load_cell', 'ZERO_OFFSET', str(offset))
    save_scale_config(cfg)
    return offset


def read_weight_g(hx, cfg):
    factor = cfg.getfloat('load_cell', 'CALIBRATION_FACTOR')
    if not math.isfinite(factor) or factor == 0:
        raise ValueError('CALIBRATION_FACTOR must be finite and nonzero')
    offset = cfg.getfloat('load_cell', 'ZERO_OFFSET', fallback=0)
    weight = (raw_mean(hx, cfg.getint('load_cell', 'READINGS_TO_AVERAGE')) - offset) / factor
    if not math.isfinite(weight):
        raise ValueError('Invalid scale calibration or reading')
    return weight


def is_weight_in_range(weight_g: float, cfg: configparser.ConfigParser) -> bool:
    """Return True if weight is within the configured 340–360 g range."""
    w_min = cfg.getfloat("load_cell", "WEIGHT_MIN_G")
    w_max = cfg.getfloat("load_cell", "WEIGHT_MAX_G")
    return w_min <= weight_g <= w_max


def main():
    from hardware_runtime import run_hardware, simulated
    parser = argparse.ArgumentParser(description="HX711 reader (grams)")
    parser.add_argument('--tare', action='store_true')
    parser.add_argument('--calibrate', action='store_true')
    args = parser.parse_args()
    cfg = _load_config()
    if simulated(cfg):
        if args.tare or args.calibrate:
            parser.error('Calibration/tare requires hardware mode on a Raspberry Pi')
        print('[SIMULATION] 350.0 g')
        return
    if args.tare or args.calibrate:
        input('Remove all weight, leave the empty tray, then press ENTER: ')
        offset = run_hardware('tare')
        if args.calibrate:
            known = float(input('Known calibration mass in grams: '))
            if not math.isfinite(known) or known <= 0:
                raise ValueError('Known mass must be positive and finite')
            input('Place the known mass, then press ENTER: ')
            factor = (run_hardware('raw') - offset) / known
            if not math.isfinite(factor) or factor == 0:
                raise ValueError('No load response; check wiring')
            cfg.set('load_cell', 'CALIBRATION_FACTOR', str(factor))
        cfg.set('load_cell', 'ZERO_OFFSET', str(offset))
        save_scale_config(cfg)
        print('Saved calibration/zero to config.ini')
        return
    try:
        while True:
            print(f"{run_hardware('weight'):.2f} g")
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()

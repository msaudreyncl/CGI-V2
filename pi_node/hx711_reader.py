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

# ADC full-scale sentinel values reported by hx711==1.1.2.3 on open-circuit/wiring errors.
_HX711_SENTINELS = frozenset((-8388608, 8388607))


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


def _stable_raw(hx, readings: int, outlier_iqr_mult: float = 1.5, samples=None) -> float:
    """Return a stable, outlier-filtered mean of `readings` HX711 ADC samples.

    Strategy:
      1. Collect `readings + 4` samples to have surplus after filtering.
      2. Discard ADC sentinel values (open-circuit / over-range markers).
      3. Remove statistical outliers using the IQR fence method.
      4. Require at least `readings` clean samples; retry once if not.
      5. Return the mean of the trimmed set.

    Raises RuntimeError if valid samples cannot be obtained after one retry.
    """
    def _collect_and_filter():
        raw = hx.get_raw_data(times=readings + 4)
        if not isinstance(raw, (list, tuple)):
            return None
        if samples is not None:
            samples.extend(raw)
        # Reject invalid data and values outside the signed 24-bit ADC range.
        clean = [
            v for v in raw
            if isinstance(v, (int, float)) and not isinstance(v, bool)
            and math.isfinite(v)
            and -8388608 < v < 8388607
        ]
        if len(clean) < readings:
            return None
        # IQR outlier rejection — skip if all values are identical (iqr == 0)
        q1, _, q3 = statistics.quantiles(clean, n=4)
        iqr = q3 - q1
        if iqr > 0:
            fence = outlier_iqr_mult * iqr
            clean = [v for v in clean if q1 - fence <= v <= q3 + fence]
        if len(clean) < readings:
            return None
        return statistics.mean(clean[:readings])

    result = _collect_and_filter()
    if result is None:
        # One retry — give the ADC a moment to settle after a noisy batch
        time.sleep(0.15)
        result = _collect_and_filter()
    if result is None:
        raise RuntimeError(
            "HX711 returned too few valid readings after filtering. "
            "Check wiring, power supply, and GPIO pin numbers in config.ini."
        )
    return result


def raw_mean(hx, readings: int = 10) -> float:
    """Backward-compatible alias for _stable_raw used by hardware_runtime._worker."""
    return _stable_raw(hx, readings)


def save_scale_config(cfg: configparser.ConfigParser) -> None:
    """Atomically replace config.ini to avoid partial writes on power loss."""
    fd, path = tempfile.mkstemp(dir=os.path.dirname(CONFIG_PATH), prefix='.scale-')
    try:
        with os.fdopen(fd, 'w') as stream:
            cfg.write(stream)
        os.replace(path, CONFIG_PATH)
    finally:
        if os.path.exists(path):
            os.unlink(path)


def tare(hx, readings: int = 20) -> float:
    """Zero the scale.

    Takes `readings` samples (default 20 for a stable baseline), saves the
    raw ADC offset to config.ini, and returns the offset value.

    Must be called with the platform in its tared state (e.g. empty tray in
    place but no beans). Never tare with the sample load present.
    """
    cfg = _load_config()
    offset = _stable_raw(hx, readings)
    cfg.set('load_cell', 'ZERO_OFFSET', str(offset))
    save_scale_config(cfg)
    return offset


def calibration_parameters(cfg):
    """Accept finite, saved calibration; factor +/-1 is a legacy placeholder.

    An explicit CALIBRATED=false disables conversion. Existing non-placeholder
    factors with a saved offset remain usable without rewriting configuration.
    """
    try:
        factor = cfg.getfloat('load_cell', 'CALIBRATION_FACTOR')
        offset = cfg.getfloat('load_cell', 'ZERO_OFFSET')
        confirmed = cfg.getboolean('load_cell', 'CALIBRATED', fallback=None)
        if (confirmed is False or not math.isfinite(factor)
                or not math.isfinite(offset) or factor == 0
                or (abs(factor) == 1 and confirmed is not True)):
            return None
        return factor, offset
    except (ValueError, configparser.Error):
        return None


def read_measurement(hx, cfg):
    """Keep the original filtered ADC mean separate from optional grams."""
    samples = []
    raw = _stable_raw(hx, cfg.getint('load_cell', 'READINGS_TO_AVERAGE', fallback=10), samples=samples)
    parameters = calibration_parameters(cfg)
    weight = None
    if parameters is not None:
        factor, offset = parameters
        weight = (raw - offset) / factor
        if not math.isfinite(weight):
            raise ValueError('Invalid scale calibration or reading')
    # Preserve original finite samples, including saturation values, for diagnosis.
    # Invalid entries become null for strict JSON serialization.
    samples = [v if isinstance(v, (int, float)) and not isinstance(v, bool)
               and math.isfinite(v) else None for v in samples]
    return {'raw_adc': raw, 'raw_samples_adc': samples, 'weight_g': weight,
            'calibrated': parameters is not None,
            'measurement_unit': 'g' if parameters is not None else 'ADC counts'}


def read_weight_g(hx, cfg: configparser.ConfigParser) -> float:
    """Convert a filtered raw ADC reading to grams using calibration parameters."""
    measurement = read_measurement(hx, cfg)
    if not measurement['calibrated']:
        raise ValueError('Weight in grams is not calibrated; use raw ADC readings')
    return measurement['weight_g']


def is_weight_in_range(weight_g: float, cfg: configparser.ConfigParser) -> bool:
    """Return True if weight is within the configured 340–360 g range."""
    w_min = cfg.getfloat("load_cell", "WEIGHT_MIN_G")
    w_max = cfg.getfloat("load_cell", "WEIGHT_MAX_G")
    return w_min <= weight_g <= w_max


def main():
    parser = argparse.ArgumentParser(description="HX711 load cell reader (grams)")
    parser.add_argument('--tare',      action='store_true', help='Zero the scale and save offset')
    parser.add_argument('--calibrate', action='store_true', help='Interactive calibration wizard')
    args = parser.parse_args()

    cfg = _load_config()

    # Simulation guard
    try:
        from hardware_runtime import simulated
        if simulated(cfg):
            if args.tare or args.calibrate:
                parser.error('Calibration/tare requires hardware mode on a Raspberry Pi')
            print('[SIMULATION] 350.0 g')
            return
    except ImportError:
        pass

    if not _ON_PI:
        parser.error(
            'RPi.GPIO / hx711 library not available — run this on a Raspberry Pi '
            'with the venv activated (source venv/bin/activate).'
        )

    import RPi.GPIO as GPIO
    try:
        hx = _build_hx711(cfg)

        if args.tare or args.calibrate:
            input('\nRemove all weight from the scale, leave only the empty tray, '
                  'then press ENTER: ')
            print('Measuring tare offset (20 samples)…', end=' ', flush=True)
            offset = tare(hx, readings=20)
            print(f'done.  Offset = {offset:.1f}')

            if args.calibrate:
                known_str = input('\nEnter the exact mass of your calibration weight in grams: ')
                known = float(known_str.strip())
                if not math.isfinite(known) or known <= 0:
                    raise ValueError('Calibration mass must be a positive finite number')
                input(f'\nPlace the {known:.1f} g calibration weight on the scale, '
                      'then press ENTER: ')
                print('Measuring calibration raw (20 samples)…', end=' ', flush=True)
                raw_with_load = _stable_raw(hx, readings=20)
                print(f'done.  Raw with load = {raw_with_load:.1f}')

                factor = (raw_with_load - offset) / known
                if not math.isfinite(factor) or factor == 0:
                    raise ValueError(
                        'Calibration factor is zero — the scale did not respond to the load. '
                        'Check wiring and ensure the load cell is properly mounted.'
                    )
                cfg.set('load_cell', 'CALIBRATED', 'true')
                cfg.set('load_cell', 'CALIBRATION_FACTOR', str(factor))
                cfg.set('load_cell', 'ZERO_OFFSET', str(offset))
                save_scale_config(cfg)
                print(f'\nCalibration saved to config.ini:')
                print(f'  CALIBRATION_FACTOR = {factor:.6f}')
                print(f'  ZERO_OFFSET        = {offset:.1f}')
                print('\nVerify by running:  python hx711_reader.py')
            else:
                print('Tare offset saved to config.ini.')
            return

        # Continuous weight display
        print('Reading weight — press Ctrl+C to stop.\n')
        try:
            while True:
                measurement = read_measurement(hx, cfg)
                print(measurement, flush=True)
                time.sleep(0.5)
        except KeyboardInterrupt:
            print('\nStopped.')
    finally:
        GPIO.cleanup()


if __name__ == '__main__':
    main()

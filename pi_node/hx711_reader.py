"""HX711 signed grams, bounded raw sampling, verified calibration and tare.

The pinned hx711==1.1.2.3 GPIO bit reader is retained. Its unbounded
get_raw_data loop is replaced with bounded calls to its single-sample reader.
"""
import argparse
import configparser
from datetime import datetime, timezone
import math
import os
import statistics
import tempfile
import time

try:
    import RPi.GPIO as GPIO
    from hx711 import HX711
    _ON_PI = True
except (ImportError, RuntimeError):
    _ON_PI = False

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.ini')

# Shared acquisition cadence for weight, tare, and calibration.
# HX711 RATE must also be wired HIGH (DVDD) for a hardware conversion rate of 80 Hz.
SAMPLE_RATE_HZ = 80
SAMPLE_INTERVAL_S = 1.0 / SAMPLE_RATE_HZ


class UnstableScaleError(RuntimeError):
    """Sensor responds, but no trustworthy measurement can be displayed."""


def _load_config():
    cfg = configparser.ConfigParser()
    if not cfg.read(CONFIG_PATH):
        raise FileNotFoundError(f'Config file not found: {CONFIG_PATH}')
    return cfg


def _safe_gain_pulses(hx, num):
    """Replace the pinned driver's recursive gain-pulse recovery with rejection.

    Timing is conservatively measured around both GPIO calls. This detects an
    overrun; Python/Linux cannot guarantee a hardware-timed clock pulse.
    """
    if num not in (1, 2, 3):
        raise ValueError('Invalid HX711 gain pulse count')
    for _ in range(num):
        started = time.perf_counter()
        try:
            GPIO.output(hx._pd_sck, True)
        finally:
            GPIO.output(hx._pd_sck, False)
        if time.perf_counter() - started >= .000050:
            hx._cgi_needs_settling = True
            raise UnstableScaleError('HX711 clock timing overrun; discarding conversion and waiting for settling')


def _build_hx711(cfg):
    if not _ON_PI:
        raise RuntimeError('HX711/GPIO driver unavailable; check the Pi venv')
    dt = cfg.getint('load_cell', 'HX711_DT_PIN')
    clock = cfg.getint('load_cell', 'HX711_SCK_PIN')
    if not (0 <= dt <= 27 and 0 <= clock <= 27) or dt == clock:
        raise ValueError('HX711 pins must be distinct BCM GPIO numbers from 0 to 27')
    class GuardedHX711(HX711):
        _set_channel_gain = _safe_gain_pulses
    hx = GuardedHX711(dout_pin=dt, pd_sck_pin=clock, gain=128, channel='A')
    # Constructor configures the gain/channel. Discard startup conversions once,
    # without reset()/power cycling before each measurement.
    raw_samples(hx, 6)
    return hx


def raw_samples(hx, readings=10, timeout=4.0):
    if not 1 <= readings <= 40:
        raise ValueError('READINGS_TO_AVERAGE must be between 1 and 40')
    deadline = time.monotonic() + timeout
    values = []
    attempts = 0
    settling = 6 if getattr(hx, '_cgi_needs_settling', False) is True else 0
    while len(values) < readings and time.monotonic() < deadline and attempts < readings * 4:
        # Keep cadence across batches and worker requests, including calibration.
        # Schedule from read start: a blocking 80 Hz ADC already supplies the delay.
        next_read = getattr(hx, '_cgi_next_read_at', 0.0)
        delay = next_read - time.monotonic()
        if delay > 0:
            time.sleep(min(delay, max(0.0, deadline - time.monotonic())))
        if time.monotonic() >= deadline:
            break
        hx._cgi_next_read_at = time.monotonic() + SAMPLE_INTERVAL_S
        attempts += 1
        try:
            value = hx._read(max_tries=20)
        except UnstableScaleError:
            hx._cgi_needs_settling = True
            raise
        # False signals a failed conversion; integer zero and -1 are valid counts.
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not -8388608 < value < 8388607):
            # The driver's False can indicate a bit-pulse timing violation and
            # unintended power-down. Abandon partial data and discard six fresh
            # conversions before trusting another complete batch.
            values.clear()
            settling = 6
            hx._cgi_needs_settling = True
            continue
        if settling:
            settling -= 1
            if not settling:
                hx._cgi_needs_settling = False
            continue
        values.append(value)
    if len(values) != readings:
        raise RuntimeError('HX711 did not return enough valid samples; check wiring, power and GPIO timing')
    return values


def filtered_sample(hx, readings=10):
    values = raw_samples(hx, readings)
    median = statistics.median(values)
    mad = statistics.median(abs(v - median) for v in values)
    # Reject isolated glitches; never average older batches into a new load.
    limit = max(3.0, 6 * mad)
    kept = [v for v in values if abs(v - median) <= limit]
    if len(kept) < math.ceil(readings * .8):
        raise UnstableScaleError('Scale moving or noisy; wait for it to settle')
    return {'raw': statistics.mean(kept), 'spread': max(kept) - min(kept),
            'rejected': readings - len(kept), 'samples': readings,
            'minimum': min(kept), 'maximum': max(kept)}


def raw_mean(hx, readings=10):
    return filtered_sample(hx, readings)['raw']


def save_scale_config(cfg):
    # Preserve unrelated configuration and replace the file atomically.
    fd, path = tempfile.mkstemp(dir=os.path.dirname(CONFIG_PATH), prefix='.scale-')
    try:
        with os.fdopen(fd, 'w') as stream:
            cfg.write(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(path, CONFIG_PATH)
    finally:
        if os.path.exists(path):
            os.unlink(path)


def calibration_values(cfg):
    if not cfg.getboolean('load_cell', 'CALIBRATION_VERIFIED', fallback=False):
        raise ValueError('Scale calibration needs verification; run hx711_reader.py --calibrate')
    factor = cfg.getfloat('load_cell', 'CALIBRATION_FACTOR')
    offset = cfg.getfloat('load_cell', 'ZERO_OFFSET')
    if not math.isfinite(factor) or factor == 0 or not math.isfinite(offset) or not -8388608 < offset < 8388607:
        raise ValueError('Invalid calibration factor/zero; recalibrate the scale')
    return factor, offset


def tolerance_g(cfg):
    tolerance = cfg.getfloat('load_cell', 'MAX_SPREAD_G', fallback=.5)
    if not math.isfinite(tolerance) or not 0 < tolerance <= 1:
        raise ValueError('MAX_SPREAD_G must be greater than 0 and at most 1 g')
    return tolerance


def weight_test_mode(cfg):
    """Explicit acquisition test; keep normal calibration checks available."""
    return cfg.getboolean('load_cell', 'WEIGHT_TEST_MODE', fallback=False)


def sample_weight(hx, cfg):
    if weight_test_mode(cfg):
        # One fresh conversion: no averaging, outlier removal, clamp or auto-tare.
        # Retain the configured conversion, even when it is not yet verified.
        factor = cfg.getfloat('load_cell', 'CALIBRATION_FACTOR')
        offset = cfg.getfloat('load_cell', 'ZERO_OFFSET')
        if not math.isfinite(factor) or factor == 0 or not math.isfinite(offset):
            raise ValueError('A finite nonzero conversion factor and finite zero are required')
        return (raw_samples(hx, 1)[0] - offset) / factor
    factor, offset = calibration_values(cfg)
    sample = filtered_sample(hx, cfg.getint('load_cell', 'READINGS_TO_AVERAGE'))
    if sample['spread'] / abs(factor) > tolerance_g(cfg):
        raise UnstableScaleError('Scale moving or noisy; wait for it to settle')
    # Keep polarity and negative net loads. No zero clamp or auto-tare.
    weight = (sample['raw'] - offset) / factor
    if not math.isfinite(weight):
        raise ValueError('Calibration produced a nonfinite weight; recalibrate')
    return weight


def read_weight_g(hx, cfg):
    return sample_weight(hx, cfg)


def collect_reference(hx, cfg):
    batches = [filtered_sample(hx, cfg.getint('load_cell', 'READINGS_TO_AVERAGE')) for _ in range(3)]
    return {'raw': statistics.mean(b['raw'] for b in batches),
            'spread': max(b['maximum'] for b in batches) - min(b['minimum'] for b in batches),
            'samples': sum(b['samples'] for b in batches),
            'rejected': sum(b['rejected'] for b in batches)}


def tare(hx, readings=10):
    cfg = _load_config()
    factor, _ = calibration_values(cfg)
    reference = collect_reference(hx, cfg)
    if reference['spread'] / abs(factor) > tolerance_g(cfg):
        raise UnstableScaleError('Tare rejected: scale is moving or noisy; remove beans and wait')
    # Verify with a fresh batch before replacing the previous persisted zero.
    check = filtered_sample(hx, cfg.getint('load_cell', 'READINGS_TO_AVERAGE'))
    if max(check['spread'], abs(check['raw'] - reference['raw'])) / abs(factor) > tolerance_g(cfg):
        raise UnstableScaleError('Tare rejected: zero moved during verification')
    cfg.set('load_cell', 'ZERO_OFFSET', str(reference['raw']))
    save_scale_config(cfg)
    return reference['raw']


def derive_calibration(empty, loaded, known_g, cfg):
    if not math.isfinite(known_g) or known_g <= 0:
        raise ValueError('Known mass must be positive and finite')
    delta = loaded['raw'] - empty['raw']
    noise = max(empty['spread'], loaded['spread'], 1.0)
    if not math.isfinite(delta) or abs(delta) < 20 * noise:
        raise ValueError('Calibration signal too small relative to noise; use a larger known mass and check mounting/wiring')
    factor = delta / known_g  # Negative is legitimate when cell polarity is reversed.
    if not math.isfinite(factor) or factor == 0:
        raise ValueError('Invalid calibration sensitivity')
    if max(empty['spread'], loaded['spread']) / abs(factor) > tolerance_g(cfg):
        raise UnstableScaleError('Calibration rejected: noise exceeds the allowed gram spread')
    return factor


def is_weight_in_range(weight_g, cfg):
    return math.isfinite(weight_g) and 340 <= weight_g <= 360


def terminal_reference(worker, label, validate=None, timeout=45.0):
    """Wait for a trustworthy CLI reference; never relax acceptance thresholds.

    Each request contains fresh batches, so a real load change replaces old data.
    Communication faults are retried with a delay, not averaged into a reference.
    """
    deadline = time.monotonic() + timeout
    last_error = 'No reference collected'
    for attempt in range(6):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            sample = worker.request('reference', timeout=min(20.0, remaining))
            print(f"{label}: {sample}", flush=True)
            if validate is not None:
                validate(sample)
            return sample
        except UnstableScaleError as exc:
            last_error = str(exc)
            print(f'UNSTABLE ({label}): {exc}', flush=True)
        except (RuntimeError, TimeoutError, OSError, EOFError) as exc:
            last_error = str(exc)
            print(f'ACQUISITION ERROR ({label}): {exc}', flush=True)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(1.0, remaining))
    raise UnstableScaleError(f'{label}: no verified reference within retry budget; {last_error}')


def verify_reference(sample, reference, factor, cfg, label):
    spread_g = sample['spread'] / abs(factor)
    shift_g = abs(sample['raw'] - reference['raw']) / abs(factor)
    print(f'{label}: spread={spread_g:.3f} g; reference shift={shift_g:.3f} g', flush=True)
    if max(spread_g, shift_g) > tolerance_g(cfg):
        raise UnstableScaleError(f'{label}: spread or reference shift exceeds {tolerance_g(cfg):.3f} g')


def main():
    from hardware_runtime import ScaleWorker, simulated
    parser = argparse.ArgumentParser(description='HX711 signed grams; stop cgi-node before CLI use')
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--tare', action='store_true')
    actions.add_argument('--calibrate', action='store_true')
    actions.add_argument('--raw', action='store_true', help='Print raw counts and spread without calibration')
    args = parser.parse_args()

    cfg = _load_config()
    if simulated(cfg):
        if args.tare or args.calibrate or args.raw:
            parser.error('This action requires hardware mode')
        print('[SIMULATION] 350.00 g')
        return
    worker = ScaleWorker()
    try:
        if args.calibrate:
            input('Remove ALL removable loads, including the tray; leave the fixed platform. Press ENTER: ')
            empty = terminal_reference(worker, 'Bare platform')
            known = float(input('Accurately known calibration mass in grams (prefer near 350 g): '))
            if not math.isfinite(known) or known <= 0:
                raise ValueError('Known mass must be positive and finite')
            input('Place ONLY that known mass on the platform, wait for settling, then press ENTER: ')
            loaded = terminal_reference(worker, 'Known load',
                lambda sample: derive_calibration(empty, sample, known, cfg))
            factor = derive_calibration(empty, loaded, known, cfg)
            print(f"Signed sensitivity: {factor:.6f} counts/g; noise spread: {loaded['spread']/abs(factor):.3f} g")
            terminal_reference(worker, 'Loaded verification',
                lambda sample: verify_reference(sample, loaded, factor, cfg, 'Loaded verification'))
            input('Remove the calibration mass; leave the bare platform. Wait, then press ENTER: ')
            unloaded = terminal_reference(worker, 'Zero return',
                lambda sample: verify_reference(sample, empty, factor, cfg, 'Zero return'))
            cfg = _load_config()
            cfg.set('load_cell', 'CALIBRATION_FACTOR', str(factor))
            cfg.set('load_cell', 'BASE_ZERO_OFFSET', str(unloaded['raw']))
            cfg.set('load_cell', 'ZERO_OFFSET', str(unloaded['raw']))
            cfg.set('load_cell', 'CALIBRATION_MASS_G', str(known))
            cfg.set('load_cell', 'CALIBRATED_AT', datetime.now(timezone.utc).isoformat())
            cfg.set('load_cell', 'CALIBRATION_VERIFIED', 'true')
            save_scale_config(cfg)
            print('Verified calibration and bare-platform zero saved to config.ini')
        elif args.tare:
            input('Remove beans; leave the empty tray (or bare platform for zeroing). Wait, then press ENTER: ')
            # Retry complete verified tare attempts; a rejected attempt saves nothing.
            deadline = time.monotonic() + 60
            for attempt in range(3):
                try:
                    worker.request('tare', timeout=min(25, max(.1, deadline - time.monotonic())))
                    break
                except UnstableScaleError as exc:
                    print(f'UNSTABLE (tare): {exc}', flush=True)
                    if attempt == 2 or time.monotonic() >= deadline:
                        raise
                    time.sleep(1)
            print('Verified tare saved; subsequent grams use this reference')
        else:
            previous = None
            while True:
                try:
                    result = worker.request('reference' if args.raw else 'weight')
                    if args.raw:
                        print(result, flush=True)
                    else:
                        now = time.monotonic()
                        if (previous is not None and now - previous[1] < 10
                                and abs(result - previous[0]) <= tolerance_g(cfg)):
                            print(f'{result:.2f} g', flush=True)
                        else:
                            print('UNSTABLE: waiting for consistent fresh weights', flush=True)
                        previous = (result, now)
                except UnstableScaleError as exc:
                    previous = None
                    print(f'UNSTABLE: {exc}', flush=True)
                except (RuntimeError, TimeoutError, OSError, EOFError) as exc:
                    previous = None
                    print(f'ACQUISITION ERROR: {exc}; retrying with fresh data', flush=True)
                    time.sleep(1)
                time.sleep(.5)
    except KeyboardInterrupt:
        pass
    except (ValueError, RuntimeError, TimeoutError) as exc:
        parser.exit(1, f'ERROR: {exc}\n')
    finally:
        worker.close()


if __name__ == '__main__':
    # Use the same exception classes as the worker's imported hx711_reader module.
    from hx711_reader import main as cli_main
    cli_main()

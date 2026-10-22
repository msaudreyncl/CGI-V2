"""Explicit simulation policy and bounded, isolated hardware operations."""
import multiprocessing
import os


def simulated(cfg):
    mode = os.getenv('CGI_HARDWARE_MODE', cfg.get('hardware', 'MODE', fallback='auto')).lower()
    if mode not in ('auto', 'hardware', 'simulation'):
        raise ValueError('hardware.MODE must be auto, hardware, or simulation')
    if mode == 'auto':
        try:
            with open('/proc/device-tree/model') as model:
                return 'Raspberry Pi' not in model.read()
        except FileNotFoundError:
            return True
    return mode == 'simulation'


def _worker(conn, operation):
    try:
        from hx711_reader import _load_config, _build_hx711, read_weight_g, raw_mean
        cfg = _load_config()
        if operation in ('weight', 'tare', 'raw'):
            import RPi.GPIO as GPIO
            try:
                hx = _build_hx711(cfg)
                result = read_weight_g(hx, cfg) if operation == 'weight' else raw_mean(
                    hx, cfg.getint('load_cell', 'READINGS_TO_AVERAGE'))
            finally:
                GPIO.cleanup()
        else:
            from camera_capture import capture_image, camera_ready
            result = capture_image() if operation == 'capture' else camera_ready()
        conn.send((True, result))
    except Exception as exc:
        conn.send((False, str(exc)))
    finally:
        conn.close()


def run_hardware(operation, timeout=4.0):
    # A stuck driver must not monopolize the HTTP server or race a retry on GPIO.
    ctx = multiprocessing.get_context('spawn')
    parent, child = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_worker, args=(child, operation), daemon=True)
    process.start()
    child.close()
    try:
        if not parent.poll(timeout):
            raise TimeoutError(f'{operation} timed out; check hardware connections')
        try:
            ok, result = parent.recv()
        except EOFError:
            raise RuntimeError(f'{operation} hardware worker exited unexpectedly')
        if not ok:
            raise RuntimeError(result)
        return result
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=1)
        if process.is_alive():
            process.kill()
            process.join()
        parent.close()

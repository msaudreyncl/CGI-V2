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
        from hx711_reader import _load_config, _build_hx711, read_weight_g, raw_mean, tare
        cfg = _load_config()
        if operation in ('weight', 'tare', 'raw'):
            import RPi.GPIO as GPIO
            try:
                hx = _build_hx711(cfg)
                if operation == 'weight':
                    result = read_weight_g(hx, cfg)
                elif operation == 'tare':
                    # tare() takes more samples for a stable baseline and saves
                    # the new offset to config.ini from inside this child process.
                    result = tare(hx, readings=cfg.getint(
                        'load_cell', 'READINGS_TO_AVERAGE', fallback=20))
                else:  # 'raw'
                    result = raw_mean(hx, cfg.getint(
                        'load_cell', 'READINGS_TO_AVERAGE', fallback=10))
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


def run_hardware(operation, timeout=12.0):
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


def _camera_worker(conn):
    """Own libcamera in one child; exit when idle so terminal tools can reuse it."""
    session = None
    try:
        from camera_capture import CameraSession
        session = CameraSession()
        while conn.poll(15):
            operation = conn.recv()
            data = session.frame(preview=operation != 'capture')
            conn.send((True, data))
    except (EOFError, BrokenPipeError):
        pass
    except Exception as exc:
        try:
            conn.send((False, str(exc)))
        except (BrokenPipeError, EOFError):
            pass
    finally:
        if session is not None:
            session.close()
        conn.close()


class CameraWorker:
    """Serialized by pi_server's camera lock. Failed workers are reaped on retry."""
    def __init__(self):
        self.process = None
        self.conn = None
        self.config = None

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=1)
            if self.process.is_alive():
                self.process.kill()
                self.process.join()
            self.process = None

    def request(self, operation, timeout=20):
        from camera_capture import _load_config
        cfg = _load_config()
        fingerprint = (dict(cfg.items('camera')) if cfg.has_section('camera') else {}, simulated(cfg))
        if self.process is None or not self.process.is_alive() or self.config != fingerprint:
            self.close()
            ctx = multiprocessing.get_context('spawn')
            self.conn, child = ctx.Pipe()
            self.process = ctx.Process(target=_camera_worker, args=(child,), daemon=True)
            self.process.start()
            child.close()
            self.config = fingerprint
        try:
            self.conn.send(operation)
            if not self.conn.poll(timeout):
                raise TimeoutError('Camera timed out; check camera connection')
            ok, result = self.conn.recv()
            if not ok:
                raise RuntimeError(result)
            return result
        except TimeoutError:
            self.close()
            raise
        except (EOFError, BrokenPipeError, OSError) as exc:
            self.close()
            raise RuntimeError('Camera disconnected; retry capture') from exc
        except Exception:
            self.close()
            raise


def _scale_worker(conn):
    """Keep the HX711 initialized across reads and tare; one GPIO owner."""
    from hx711_reader import (_load_config, _build_hx711, read_weight_g,
                              collect_reference, filtered_sample, read_measurement, tare, UnstableScaleError)
    try:
        import RPi.GPIO as GPIO
        if multiprocessing.current_process().name != 'MainProcess':
            import signal
            def stop_worker(signum, frame):
                raise SystemExit(0)
            signal.signal(signal.SIGTERM, stop_worker)
        hx = _build_hx711(_load_config())
        while True:
            operation = conn.recv()
            if operation == 'close':
                break
            try:
                cfg = _load_config()  # Reload persisted zero/factor without resetting ADC.
                if operation == 'measurement':
                    result = read_measurement(hx, cfg)
                elif operation == 'weight':
                    result = read_weight_g(hx, cfg)
                elif operation == 'probe':
                    result = filtered_sample(hx, cfg.getint('load_cell', 'READINGS_TO_AVERAGE'))
                elif operation == 'reference':
                    result = collect_reference(hx, cfg)
                elif operation == 'tare':
                    result = tare(hx)
                else:
                    raise ValueError('Unknown scale operation')
                conn.send((True, result, None))
            except UnstableScaleError as exc:
                conn.send((False, str(exc), 'unstable'))
            except ValueError as exc:
                conn.send((False, str(exc), 'calibration'))
    except (EOFError, BrokenPipeError, KeyboardInterrupt):
        pass
    except Exception as exc:
        try:
            conn.send((False, str(exc), 'sensor'))
        except (BrokenPipeError, EOFError):
            pass
    finally:
        if 'GPIO' in locals():
            GPIO.cleanup()
        conn.close()


class ScaleWorker:
    """Serialized by the server scale lock; recreate only after faults/pin changes."""
    def __init__(self):
        self.process = None
        self.conn = None
        self.pins = None

    def close(self):
        if self.process is not None:
            if self.process.is_alive() and self.conn is not None:
                try:
                    self.conn.send('close')
                except (BrokenPipeError, EOFError, OSError):
                    pass
                # Let the owner reset its GPIO before resorting to termination.
                self.process.join(timeout=.5)
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=1)
            if self.process.is_alive():
                self.process.kill()
                self.process.join()
            self.process = None
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def request(self, operation, timeout=None):
        from hx711_reader import _load_config, UnstableScaleError
        cfg = _load_config()
        pins = (cfg.getint('load_cell', 'HX711_DT_PIN'), cfg.getint('load_cell', 'HX711_SCK_PIN'))
        if self.process is None or not self.process.is_alive() or self.pins != pins:
            self.close()
            ctx = multiprocessing.get_context('spawn')
            self.conn, child = ctx.Pipe()
            self.process = ctx.Process(target=_scale_worker, args=(child,), daemon=True)
            self.process.start()
            child.close()
            self.pins = pins
        timeout = timeout if timeout is not None else {'measurement': 8, 'weight': 8, 'probe': 8, 'reference': 20, 'tare': 25}[operation]
        try:
            self.conn.send(operation)
            if not self.conn.poll(timeout):
                raise TimeoutError('HX711 timed out; check wiring, power and GPIO timing')
            ok, result, kind = self.conn.recv()
            if not ok:
                if kind == 'unstable':
                    raise UnstableScaleError(result)
                if kind == 'calibration':
                    raise ValueError(result)
                raise RuntimeError(result)
            return result
        except (UnstableScaleError, ValueError):
            # Keep the same ADC reference and allow settling or calibration retry.
            raise
        except Exception:
            self.close()
            raise

"""Existing Pi weight/capture HTTP interface, with bounded hardware access.

GET /weight includes independent camera/scale readiness. POST /weight tares the
empty platform. POST /capture accepts view A or B. Run one server per Pi.
"""
import base64
import json
import math
import secrets
from datetime import datetime, timezone
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from hardware_runtime import CameraWorker, ScaleWorker, simulated
from hx711_reader import (_load_config, UnstableScaleError, calibration_values,
                          derive_calibration, verify_reference, save_scale_config, weight_test_mode)

_scale_lock = threading.Lock()
_scale_worker = ScaleWorker()
_camera_lock = threading.Lock()
_calibration = None
_last_weight = None
_last_read_at = 0
_camera_checked_at = 0
_camera_status = 'error'
_camera_error = None
_camera_worker = CameraWorker()


def _read_weight():
    global _last_weight, _last_read_at
    with _scale_lock:
        try:
            cfg = _load_config()
            if _calibration and time.monotonic() < _calibration['expires']:
                raise UnstableScaleError('Calibration in progress')
            if not simulated(cfg) and not weight_test_mode(cfg):
                try:
                    calibration_values(cfg)
                except ValueError:
                    # A responding ADC can be calibrated in Step 2 even before
                    # it has a valid grams conversion. Never fabricate a weight.
                    _scale_worker.request('probe')
                    raise UnstableScaleError('Calibration required — calibrate the scale in Step 2')
            weight = 350.0 if simulated(cfg) else _scale_worker.request('weight')
            if not math.isfinite(weight):
                raise ValueError('Scale returned a nonfinite reading')
            now = time.monotonic()
            stable = (_last_weight is not None and now - _last_read_at < 10
                      and abs(weight - _last_weight) <= 0.5)
            _last_weight, _last_read_at = weight, now
            return weight, stable, 340 <= weight <= 360
        except Exception:
            _last_weight = None
            raise


def _camera_readiness():
    global _camera_checked_at, _camera_status, _camera_error
    if simulated(_load_config()):
        _camera_error = None
        return 'ready'
    # Do not contend with an active capture; a fresh capture is also a probe.
    with _camera_lock:
        if time.monotonic() - _camera_checked_at > 2:
            try:
                _camera_worker.request('preview', timeout=8)
                _camera_status = 'ready'
                _camera_error = None
            except Exception as exc:
                _camera_status = 'error'
                _camera_error = str(exc)
                print(f'[camera readiness] {_camera_error}', flush=True)
            _camera_checked_at = time.monotonic()
        return _camera_status


def _capture_image_b64(preview=False):
    global _camera_status, _camera_checked_at, _camera_error
    if not _camera_lock.acquire(blocking=False):
        raise RuntimeError('Camera is busy; retry after the current capture')
    try:
        data = _camera_worker.request('preview' if preview else 'capture', timeout=20)
        _camera_status = 'ready'
        _camera_error = None
        return base64.b64encode(data).decode('ascii')
    except Exception as exc:
        _camera_status = 'error'
        _camera_error = str(exc)
        raise
    finally:
        _camera_checked_at = time.monotonic()
        _camera_lock.release()


def _tare():
    global _last_weight
    with _scale_lock:
        cfg = _load_config()
        if _calibration and time.monotonic() < _calibration['expires']:
            raise ValueError('Finish or cancel calibration before taring')
        if not simulated(cfg):
            _scale_worker.request('tare')
        _last_weight = None
    return {'tared': True, 'simulated': simulated(cfg)}


def _weight_action(body):
    """Use the existing weight resource; save only after load and zero checks."""
    global _calibration, _last_weight
    action = body['action']
    if action == 'tare':
        return _tare()
    with _scale_lock:
        _last_weight = None
        cfg = _load_config()
        if simulated(cfg):
            raise ValueError('Calibration requires real HX711 hardware; disable simulation')
        if action == 'calibration_zero':
            if _calibration and time.monotonic() < _calibration['expires']:
                raise ValueError('Calibration already active; finish or cancel it')
            empty = _scale_worker.request('reference')
            _calibration = {'token': secrets.token_urlsafe(24), 'empty': empty,
                            'expires': time.monotonic() + 600, 'stage': 'load'}
            return {'token': _calibration['token'], 'stage': 'load'}
        session = _calibration
        if not session or body.get('token') != session['token']:
            raise ValueError('Calibration session missing; start again')
        if action == 'calibration_cancel':
            _calibration = None
            return {'cancelled': True}
        if time.monotonic() >= session['expires']:
            _calibration = None
            raise ValueError('Calibration expired; start again')
        if action == 'calibration_load':
            if session['stage'] != 'load':
                raise ValueError('Remove the reference mass and verify zero')
            known = body.get('known_g')
            if isinstance(known, bool) or not isinstance(known, (float, int)):
                raise ValueError('Known mass must be positive and finite')
            if not math.isfinite(known) or known <= 0:
                raise ValueError('Known mass must be positive and finite')
            loaded = _scale_worker.request('reference')
            factor = derive_calibration(session['empty'], loaded, known, cfg)
            check = _scale_worker.request('reference')
            verify_reference(check, loaded, factor, cfg, 'Loaded verification')
            session.update(stage='finish', factor=factor, known=known)
            return {'stage': 'finish'}
        if action == 'calibration_finish':
            if session['stage'] != 'finish':
                raise ValueError('Measure the known reference mass first')
            zero = _scale_worker.request('reference')
            verify_reference(zero, session['empty'], session['factor'], cfg, 'Zero return')
            for key, value in {
                'CALIBRATION_FACTOR': session['factor'], 'ZERO_OFFSET': zero['raw'],
                'BASE_ZERO_OFFSET': zero['raw'], 'CALIBRATION_MASS_G': session['known'],
                'CALIBRATED_AT': datetime.now(timezone.utc).isoformat(),
                'CALIBRATION_VERIFIED': 'true',
            }.items():
                cfg.set('load_cell', key, str(value))
            save_scale_config(cfg)
            _calibration = None
            return {'calibrated': True, 'simulated': False}
        raise ValueError('Unknown scale action')


class PiRequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, status, payload):
        body = json.dumps(payload, allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        try:
            self._get_readiness()
        except Exception as exc:
            # Configuration/probe failures must return JSON, not close the socket.
            self._send_json(503, {'scale': 'error', 'camera': 'error',
                                  'error': str(exc), 'camera_error': str(exc)})

    def _get_readiness(self):
        if self.path != '/weight':
            return self._send_json(404, {'error': 'Not found'})
        # Check devices concurrently so a slow/disconnected scale cannot consume
        # the camera's portion of the backend's readiness timeout.
        with ThreadPoolExecutor(max_workers=1) as pool:
            camera = pool.submit(_camera_readiness)
            cfg = _load_config()
            payload = {'scale': 'error', 'simulated': simulated(cfg),
                       'weight_test_mode': weight_test_mode(cfg) and not simulated(cfg)}
            code = 200
            try:
                weight, stable, in_range = _read_weight()
                payload.update(weight_g=weight, measured_at=datetime.now(timezone.utc).isoformat(), stable=stable,
                               in_range=in_range, scale='ready')
                if not payload['simulated']:
                    print(json.dumps({'event': 'hx711_reading', 'weight_g': weight,
                                      'measured_at': payload['measured_at']}, allow_nan=False), flush=True)
            except UnstableScaleError as exc:
                payload.update(error=str(exc), measurement_state='unstable', scale='ready',
                               weight_g=None, stable=False, in_range=False)
            except Exception as exc:
                payload.update(error=str(exc), weight_g=None, stable=False, in_range=False)
                code = 503
            payload.update(camera=camera.result(), camera_error=_camera_error)
        self._send_json(code, payload)

    def do_POST(self):
        if self.path not in ('/capture', '/weight'):
            return self._send_json(404, {'error': 'Not found'})
        try:
            length = int(self.headers.get('Content-Length', 0))
            if length < 0 or length > 1024:
                raise ValueError('Request body too large')
            self.connection.settimeout(5)
            body = json.loads(self.rfile.read(length) if length else b'{}')
            if not isinstance(body, dict):
                raise ValueError('Expected a JSON object')
            if self.path == '/weight':
                if body.get('action') not in ('tare', 'calibration_zero', 'calibration_load',
                                               'calibration_finish', 'calibration_cancel'):
                    raise ValueError('Unknown scale action')
            elif not isinstance(body.get('preview', False), bool):
                raise ValueError('preview must be a boolean')
            elif body.get('view') not in ('A', 'B'):
                raise ValueError("view must be 'A' or 'B'")
        except (ValueError, TimeoutError) as exc:
            return self._send_json(400, {'error': str(exc)})
        try:
            if self.path == '/weight':
                payload = _weight_action(body)
            else:
                payload = {'image_b64': _capture_image_b64(preview=body.get('preview', False)), 'view': body['view'],
                           'preview': body.get('preview', False),
                           'simulated': simulated(_load_config())}
            self._send_json(200, payload)
        except Exception as exc:
            self._send_json(503, {'error': str(exc)})


def main():
    cfg = _load_config()
    host = cfg.get('server', 'PI_SERVER_HOST', fallback='0.0.0.0')
    port = cfg.getint('server', 'PI_SERVER_PORT', fallback=5000)
    print(f"CGI Pi server on {host}:{port}; simulation={simulated(cfg)}", flush=True)
    server = ThreadingHTTPServer((host, port), PiRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        _camera_worker.close()
        _scale_worker.close()


if __name__ == '__main__':
    main()

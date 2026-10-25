"""Existing Pi weight/capture HTTP interface, with bounded hardware access.

GET /weight includes independent camera/scale readiness. POST /weight tares the
empty platform. POST /capture accepts view A or B. Run one server per Pi.
"""
import base64
import json
import math
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from hardware_runtime import CameraWorker, run_hardware, simulated
from hx711_reader import _load_config, save_scale_config

_scale_lock = threading.Lock()
_camera_lock = threading.Lock()
_last_weight = None
_last_read_at = 0
_camera_checked_at = 0
_camera_status = 'error'
_camera_error = None
_camera_worker = CameraWorker()


def _read_weight():
    global _last_weight, _last_read_at
    cfg = _load_config()
    with _scale_lock:
        try:
            measurement = ({'weight_g': 350.0, 'raw_adc': None, 'calibrated': False,
                            'measurement_unit': 'g'} if simulated(cfg)
                           else run_hardware('measurement'))
            weight = measurement['weight_g']
            if weight is None:
                _last_weight = None
                return dict(measurement, stable=False, in_range=False)
            if not math.isfinite(weight):
                raise ValueError('Scale returned a nonfinite reading')
            now = time.monotonic()
            stable = (_last_weight is not None and now - _last_read_at < 10
                      and abs(weight - _last_weight) <= 0.5)
            _last_weight, _last_read_at = weight, now
            return dict(measurement, stable=stable, in_range=340 <= weight <= 360)
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
        if not simulated(cfg):
            # tare() inside the child process saves the new ZERO_OFFSET to
            # config.ini atomically; no second write is needed here.
            run_hardware('tare')
        _last_weight = None
    return {'tared': True, 'simulated': simulated(cfg)}


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
        if self.path != '/weight':
            return self._send_json(404, {'error': 'Not found'})
        payload = {'camera': _camera_readiness(), 'camera_error': _camera_error,
                   'scale': 'error', 'simulated': simulated(_load_config())}
        try:
            measurement = _read_weight()
            payload.update(measurement, scale='ready')
            self._send_json(200, payload)
        except Exception as exc:
            payload.update(error=str(exc), raw_adc=None, weight_g=None, calibrated=False, stable=False, in_range=False)
            self._send_json(503, payload)

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
                if body.get('action') != 'tare':
                    raise ValueError('action must be tare')
            elif not isinstance(body.get('preview', False), bool):
                raise ValueError('preview must be a boolean')
            elif body.get('view') not in ('A', 'B'):
                raise ValueError("view must be 'A' or 'B'")
        except (ValueError, TimeoutError) as exc:
            return self._send_json(400, {'error': str(exc)})
        try:
            if self.path == '/weight':
                payload = _tare()
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


if __name__ == '__main__':
    main()

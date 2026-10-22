"""Pi HTTP -> authenticated hardware proxy -> dual analysis -> stored transaction.

Real GPIO/camera and trained YOLO inference are intentionally substituted here.
"""
import base64
import configparser
import io
from pathlib import Path
import sys
import threading
import time
from unittest.mock import AsyncMock, Mock, patch

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'pi_node'))
import pi_server
import hx711_reader
import hardware_runtime
from tests.test_integration import client, admin_token, officer_token, farmer_id, _TestSession, _auth_header


def config():
    cfg = configparser.ConfigParser()
    cfg.read_dict({'hardware': {'MODE': 'simulation'}, 'load_cell': {
        'CALIBRATION_FACTOR': '-100', 'ZERO_OFFSET': '10000', 'READINGS_TO_AVERAGE': '10'}})
    return cfg


def test_pinned_driver_raw_conversion_and_invalid_data():
    hx = Mock()
    hx.get_raw_data.return_value = [-25000] * 10
    assert hx711_reader.read_weight_g(hx, config()) == 350
    hx.get_raw_data.return_value = [False] * 10
    with pytest.raises(RuntimeError):
        hx711_reader.read_weight_g(hx, config())
    cfg = config()
    cfg.set('load_cell', 'CALIBRATION_FACTOR', '0')
    with pytest.raises(ValueError):
        hx711_reader.read_weight_g(hx, cfg)


def test_hardware_mode_never_silently_simulates(monkeypatch):
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'hardware')
    assert hardware_runtime.simulated(config()) is False
    monkeypatch.setattr(pi_server, 'run_hardware', Mock(side_effect=RuntimeError('Disconnected')))
    with pytest.raises(RuntimeError, match='Disconnected'):
        pi_server._read_weight()
    assert pi_server._last_weight is None
    assert pi_server._camera_readiness() == 'error'


def test_worker_deadline_reaps_stuck_driver():
    # A near-zero deadline expires before spawn can import/access any drivers.
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        hardware_runtime.run_hardware('weight', timeout=0)
    assert time.monotonic() - started < 3


@pytest.fixture
def pi_http(monkeypatch):
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'simulation')
    pi_server._last_weight = None
    server = pi_server.ThreadingHTTPServer(('127.0.0.1', 0), pi_server.PiRequestHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    from routers import hardware
    monkeypatch.setattr(hardware.settings, 'PI_NODE_URL', f'http://127.0.0.1:{server.server_port}')
    monkeypatch.setattr(hardware, '_check_printer', AsyncMock(return_value='warning'))
    yield server
    server.shutdown()
    server.server_close()
    thread.join()


def test_hardware_to_saved_dual_transaction(client, officer_token, farmer_id, pi_http, monkeypatch, tmp_path):
    from routers import inspection
    from models.transaction import Transaction
    from models.pending_transaction import PendingTransaction
    monkeypatch.setattr(inspection.settings, 'UPLOAD_DIR', str(tmp_path))
    headers = _auth_header(officer_token)
    status = client.get('/api/hardware/status', headers=headers).json()
    assert status == {'camera': 'ready', 'scale': 'ready', 'printer': 'warning', 'simulated': True}
    assert client.post('/api/hardware/weight', headers=headers, json={'action': 'tare'}).json()['tared']
    first = client.get('/api/hardware/weight', headers=headers).json()
    second = client.get('/api/hardware/weight', headers=headers).json()
    assert first['stable'] is False
    assert second['stable'] and second['weight_g'] == 350
    init = client.post('/api/transaction/init', headers=headers, json={'farmer_id': farmer_id})
    assert init.status_code == 201, init.text
    pending_id = init.json()['pending_id']
    for invalid in [339.9, 360.1]:
        assert client.put(f'/api/transaction/{pending_id}/weight', headers=headers, json={'weight_g': invalid}).status_code == 422
    for valid in [340, 360, second['weight_g']]:
        assert client.put(f'/api/transaction/{pending_id}/weight', headers=headers, json={'weight_g': valid}).status_code == 200
    images = []
    for view in ('A', 'B'):
        captured = client.post('/api/hardware/capture', headers=headers, json={'view': view})
        assert captured.status_code == 200, captured.text
        images.append(captured.json()['image_b64'])
        Image.open(io.BytesIO(base64.b64decode(images[-1]))).verify()
    seen = []
    def detect(path):
        Image.open(path).verify()
        seen.append(path)
        return {'total_beans': 100, 'class_counts': {'black_bean': 2}}, b''
    pricing = {'price_per_kg': 255, 'market_rate_per_kg': 300, 'multiplier': .85,
               'currency': 'PHP', 'source': 'manual'}
    with patch('routers.inspection.run_detection_with_annotation', side_effect=detect), patch(
        'services.pricing.suggest_price', new=AsyncMock(return_value=pricing)
    ):
        analyzed = client.post('/api/inspection/capture-dual', headers=headers, json={
            'pending_id': pending_id, 'image_a_b64': images[0], 'image_b_b64': images[1]})
    assert analyzed.status_code == 201, analyzed.text
    result = analyzed.json()
    assert len(seen) == 2
    assert result['sample_weight_g'] == 350 and result['txn_number'] == init.json()['txn_number']
    with _TestSession() as db:
        txn = db.get(Transaction, result['txn_id'])
        assert float(txn.weight_kg) == .35
        assert txn.inspection_id == result['id']
        assert float(db.get(PendingTransaction, pending_id).weight_g) == 350


def test_disconnections_and_recovery(client, officer_token, pi_http, monkeypatch):
    headers = _auth_header(officer_token)
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'hardware')
    monkeypatch.setattr(pi_server, 'run_hardware', Mock(side_effect=TimeoutError('Device disconnected')))
    pi_server._camera_checked_at = 0
    status = client.get('/api/hardware/status', headers=headers).json()
    assert status['camera'] == status['scale'] == 'error'
    assert client.get('/api/hardware/weight', headers=headers).status_code == 503
    assert client.post('/api/hardware/capture', headers=headers, json={'view': 'A'}).status_code == 502
    assert client.post('/api/hardware/weight', headers=headers, json={'action': 'tare'}).status_code == 503
    assert client.post('/api/hardware/capture', headers=headers, json={'view': 'C'}).status_code == 400
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'simulation')
    assert client.get('/api/hardware/weight', headers=headers).status_code == 200


def test_tare_persists_zero_and_clears_stability(monkeypatch, tmp_path):
    cfg = config()
    target = tmp_path / 'config.ini'
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'hardware')
    monkeypatch.setattr(hx711_reader, 'CONFIG_PATH', str(target))
    monkeypatch.setattr(pi_server, '_load_config', lambda: cfg)
    monkeypatch.setattr(pi_server, 'run_hardware', Mock(return_value=12345.5))
    pi_server._last_weight = 350
    assert pi_server._tare()['tared']
    assert pi_server._last_weight is None
    saved = configparser.ConfigParser()
    saved.read(target)
    assert saved.getfloat('load_cell', 'ZERO_OFFSET') == 12345.5
    assert saved.getfloat('load_cell', 'CALIBRATION_FACTOR') == -100


def test_picamera_autofocus_capture_and_cleanup(monkeypatch):
    import camera_capture
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'hardware')
    monkeypatch.setattr(camera_capture, '_ON_PI', True)
    cam = Mock()
    cam.autofocus_cycle.return_value = True
    cam.capture_file.side_effect = lambda stream, **kwargs: stream.write(b'jpeg-test')
    monkeypatch.setattr(camera_capture, 'Picamera2', Mock(return_value=cam), raising=False)
    monkeypatch.setattr(camera_capture.time, 'sleep', lambda _: None)
    assert camera_capture.capture_image() == b'jpeg-test'
    cam.autofocus_cycle.assert_called_once()
    cam.close.assert_called_once()
    cam.reset_mock()
    cam.autofocus_cycle.return_value = False
    with pytest.raises(RuntimeError, match='autofocus'):
        camera_capture.capture_image()
    cam.close.assert_called_once()

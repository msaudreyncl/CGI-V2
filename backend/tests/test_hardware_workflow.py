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
import types
from unittest.mock import AsyncMock, Mock, patch

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'pi_node'))
import pi_server
import hx711_reader
import hardware_runtime
from tests.test_integration import client, admin_token, officer_token, farmer_id, _TestSession, _auth_header


@pytest.fixture(autouse=True)
def normal_weight_gate(monkeypatch):
    from routers import transaction_workflow
    monkeypatch.setattr(transaction_workflow.settings, 'WEIGHT_TEST_MODE', False)


def config():
    cfg = configparser.ConfigParser()
    cfg.read_dict({'hardware': {'MODE': 'simulation'}, 'load_cell': {
        'STABILITY_DURATION_S': '0.000001', 'CALIBRATION_FACTOR': '-100', 'ZERO_OFFSET': '10000', 'READINGS_TO_AVERAGE': '10',
        'CALIBRATION_VERIFIED': 'true', 'HX711_DT_PIN': '5', 'HX711_SCK_PIN': '6'}})
    return cfg


def test_pinned_driver_raw_conversion_and_invalid_data():
    hx = Mock(_cgi_next_read_at=0.0)
    hx._read.return_value = -25000
    assert hx711_reader.read_weight_g(hx, config()) == 350
    hx._read.return_value = False
    with pytest.raises(RuntimeError):
        hx711_reader.read_weight_g(hx, config())
    cfg = config()
    cfg.set('load_cell', 'CALIBRATION_FACTOR', '0')
    with pytest.raises(ValueError):
        hx711_reader.read_weight_g(hx, cfg)


def test_hardware_mode_never_silently_simulates(monkeypatch):
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'hardware')
    assert hardware_runtime.simulated(config()) is False
    monkeypatch.setattr(pi_server._scale_worker, 'request', Mock(side_effect=RuntimeError('Disconnected')))
    with pytest.raises(RuntimeError, match='Disconnected'):
        pi_server._read_weight()
    assert pi_server._last_weight is None
    monkeypatch.setattr(pi_server._camera_worker, 'request', Mock(side_effect=RuntimeError('Disconnected')))
    pi_server._camera_checked_at = 0
    assert pi_server._camera_readiness() == 'error'


def test_worker_deadline_reaps_stuck_driver():
    # A near-zero deadline expires before spawn can import/access any drivers.
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        hardware_runtime.run_hardware('weight', timeout=0)
    assert time.monotonic() - started < 3


@pytest.fixture
def pi_http(monkeypatch):
    original_load = pi_server._load_config
    def normal_config():
        cfg = original_load()
        if cfg.has_section('load_cell'):
            cfg.set('load_cell', 'WEIGHT_SENSOR_TEST_MODE', 'false')
        return cfg
    monkeypatch.setattr(pi_server, '_load_config', normal_config)
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'simulation')
    pi_server._last_weight = None
    worker = hardware_runtime.CameraWorker()
    monkeypatch.setattr(pi_server, '_camera_worker', worker)
    scale_worker = hardware_runtime.ScaleWorker()
    monkeypatch.setattr(pi_server, '_scale_worker', scale_worker)
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
    worker.close()
    scale_worker.close()


def test_hardware_to_saved_dual_transaction(client, officer_token, farmer_id, pi_http, monkeypatch, tmp_path):
    from routers import inspection
    from models.transaction import Transaction
    from models.pending_transaction import PendingTransaction
    monkeypatch.setattr(inspection.settings, 'UPLOAD_DIR', str(tmp_path))
    headers = _auth_header(officer_token)
    status = client.get('/api/hardware/status', headers=headers).json()
    assert status == {'camera': 'ready', 'scale': 'ready', 'printer': 'warning', 'simulated': True, 'details': {}, 'sensor_test_mode': False}
    # Explicit mocked physical payloads; simulated service readings cannot transact.
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'hardware')
    monkeypatch.setattr(pi_server, '_load_config', config)
    monkeypatch.setattr(pi_server._scale_worker, 'request', Mock(return_value={
        'weight_g':350.0, 'calibrated':True, 'measurement_state':'calibrated'}))
    from tests.test_integration import _tiny_jpeg_b64
    monkeypatch.setattr(pi_server._camera_worker, 'request', Mock(return_value=base64.b64decode(_tiny_jpeg_b64())))
    assert client.post('/api/hardware/weight', headers=headers, json={'action': 'tare'}).json()['tared']
    first = client.get('/api/hardware/weight', headers=headers).json()
    second = client.get('/api/hardware/weight', headers=headers).json()
    assert first['stable'] is False
    assert second['stable'] and second['weight_g'] == 350
    init = client.post('/api/transaction/init', headers=headers, json={'farmer_id': farmer_id})
    assert init.status_code == 201, init.text
    pending_id = init.json()['pending_id']
    # Submitted grams are untrusted: every save re-reads and stores actual 350 g.
    for submitted in [339.9, 360.1, 340, 360, 350]:
        saved = client.put(f'/api/transaction/{pending_id}/weight', headers=headers, json={'weight_g':submitted})
        assert saved.status_code == 200, saved.text
        assert saved.json()['weight_g'] == 350
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
    assert [base64.b64encode(Path(path).read_bytes()).decode() for path in seen] == images
    assert result['sample_weight_g'] == 350 and result['txn_number'] == init.json()['txn_number']
    with _TestSession() as db:
        txn = db.get(Transaction, result['txn_id'])
        assert float(txn.weight_kg) == .35
        assert txn.inspection_id == result['id']
        assert float(db.get(PendingTransaction, pending_id).weight_g) == 350


def test_disconnections_and_recovery(client, officer_token, pi_http, monkeypatch):
    headers = _auth_header(officer_token)
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'hardware')
    monkeypatch.setattr(pi_server._scale_worker, 'request', Mock(side_effect=TimeoutError('Device disconnected')))
    monkeypatch.setattr(pi_server._camera_worker, 'request', Mock(side_effect=TimeoutError('Camera disconnected')))
    pi_server._camera_checked_at = 0
    status = client.get('/api/hardware/status', headers=headers).json()
    assert status['camera'] == status['scale'] == 'error'
    assert status['details']['camera'] == 'Camera disconnected'
    assert status['details']['scale'] == 'Device disconnected'
    assert client.get('/api/hardware/weight', headers=headers).status_code == 503
    assert client.post('/api/hardware/capture', headers=headers, json={'view': 'A'}).status_code == 502
    assert client.post('/api/hardware/weight', headers=headers, json={'action': 'tare'}).status_code == 503
    assert client.post('/api/hardware/capture', headers=headers, json={'view': 'C'}).status_code == 400
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'simulation')
    assert client.get('/api/hardware/weight', headers=headers).status_code == 200


def test_server_tare_uses_same_worker_and_clears_stability(monkeypatch, tmp_path):
    cfg = config()
    target = tmp_path / 'config.ini'
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'hardware')
    monkeypatch.setattr(hx711_reader, 'CONFIG_PATH', str(target))
    monkeypatch.setattr(pi_server, '_load_config', lambda: cfg)
    monkeypatch.setattr(pi_server._scale_worker, 'request', Mock(return_value=12345.5))
    pi_server._last_weight = 350
    assert pi_server._tare()['tared']
    assert pi_server._last_weight is None
    pi_server._scale_worker.request.assert_called_once_with('tare')


def test_picamera_autofocus_capture_and_cleanup(monkeypatch):
    import camera_capture
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'hardware')
    monkeypatch.setattr(camera_capture, '_ON_PI', True)
    cfg = config()
    cfg.add_section('camera')
    cfg.set('camera', 'FOCUS_MODE', 'auto')
    monkeypatch.setattr(camera_capture, '_load_config', lambda: cfg)
    monkeypatch.setitem(sys.modules, 'libcamera', types.SimpleNamespace(controls=types.SimpleNamespace(
        AfModeEnum=types.SimpleNamespace(Manual=0, Auto=1, Continuous=2))))
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


def test_preview_reuses_capture_worker_and_does_not_save(client, officer_token, pi_http):
    headers = _auth_header(officer_token)
    from models.inspection import Inspection
    with _TestSession() as db:
        before = db.query(Inspection).count()
    preview = client.post('/api/hardware/capture', headers=headers,
                          json={'view': 'A', 'preview': True})
    assert preview.status_code == 200, preview.text
    assert preview.json()['preview'] is True and preview.json()['simulated'] is True
    image = Image.open(io.BytesIO(base64.b64decode(preview.json()['image_b64'])))
    assert image.width <= 640 and image.height <= 360
    pid = pi_server._camera_worker.process.pid
    still = client.post('/api/hardware/capture', headers=headers, json={'view': 'B'})
    assert still.status_code == 200, still.text
    assert still.json()['preview'] is False
    assert pi_server._camera_worker.process.pid == pid
    full = Image.open(io.BytesIO(base64.b64decode(still.json()['image_b64'])))
    assert full.width > image.width
    with _TestSession() as db:
        assert db.query(Inspection).count() == before
    assert client.post('/api/hardware/capture', json={'view': 'A', 'preview': True}).status_code in (401, 403)


def test_camera_worker_deadline_and_restart(monkeypatch):
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'simulation')
    worker = hardware_runtime.CameraWorker()
    try:
        with pytest.raises(TimeoutError):
            worker.request('preview', timeout=0)
        assert worker.process is None and worker.conn is None
        assert worker.request('preview').startswith(b'\xff\xd8')
        assert worker.request('capture').startswith(b'\xff\xd8')
    finally:
        worker.close()


def test_manual_picamera_configuration_matches_working_terminal(monkeypatch):
    import camera_capture
    cfg = config()
    cfg.add_section('camera')
    cfg.set('camera', 'FOCUS_MODE', 'manual')
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'hardware')
    monkeypatch.setattr(camera_capture, '_ON_PI', True)
    monkeypatch.setitem(sys.modules, 'libcamera', types.SimpleNamespace(controls=types.SimpleNamespace(
        AfModeEnum=types.SimpleNamespace(Manual=0, Auto=1, Continuous=2))))
    cam = Mock()
    image = io.BytesIO()
    Image.new('RGB', (1920, 1080)).save(image, format='JPEG')
    cam.capture_file.side_effect = lambda stream, **kwargs: stream.write(image.getvalue())
    monkeypatch.setattr(camera_capture, 'Picamera2', Mock(return_value=cam), raising=False)
    monkeypatch.setattr(camera_capture.time, 'sleep', lambda _: None)
    session = camera_capture.CameraSession(cfg)
    try:
        assert session.frame().startswith(b'\xff\xd8')
        small = Image.open(io.BytesIO(session.frame(preview=True)))
        assert small.size == (640, 360)
        cam.autofocus_cycle.assert_not_called()
        kwargs = cam.create_still_configuration.call_args.kwargs
        assert kwargs['controls'] == {'AfMode': 0}
        assert kwargs['queue'] is False
    finally:
        session.close()
    cam.close.assert_called_once()


def test_readiness_reports_transport_and_outdated_service_errors(client, officer_token):
    import httpx
    headers = _auth_header(officer_token)
    for failure, expected in [(httpx.ConnectError('refused'), 'Cannot reach Pi service'),
                              (httpx.ReadTimeout('timeout'), 'timed out')]:
        with patch('routers.hardware._pi_get', new=AsyncMock(side_effect=failure)), patch(
            'routers.hardware._check_printer', new=AsyncMock(return_value='warning')):
            response = client.get('/api/hardware/status', headers=headers)
        assert response.status_code == 200
        assert response.json()['camera'] == 'error'
        assert expected in response.json()['details']['camera']
    with patch('routers.hardware._pi_get', new=AsyncMock(return_value={'weight_g':350})), patch(
        'routers.hardware._check_printer', new=AsyncMock(return_value='warning')):
        response = client.get('/api/hardware/status', headers=headers)
    assert response.json()['camera'] == 'error'
    assert 'outdated' in response.json()['details']['camera']


def test_camera_readiness_is_independent_of_failed_scale(client, officer_token, pi_http, monkeypatch):
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'hardware')
    monkeypatch.setattr(pi_server._scale_worker, 'request', Mock(side_effect=RuntimeError('HX711 disconnected')))
    monkeypatch.setattr(pi_server._camera_worker, 'request', Mock(return_value=b'jpeg'))
    pi_server._camera_checked_at = 0
    response = client.get('/api/hardware/status', headers=_auth_header(officer_token))
    assert response.status_code == 200
    assert response.json()['camera'] == 'ready'
    assert response.json()['scale'] == 'error'
    assert 'camera' not in response.json()['details']
    assert response.json()['details']['scale'] == 'HX711 disconnected'


def test_signed_filtered_weight_and_unstable_state_reach_frontend_api(client, officer_token, pi_http, monkeypatch):
    from hx711_reader import UnstableScaleError
    monkeypatch.setattr(pi_server, '_load_config', config)
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'hardware')
    monkeypatch.setattr(pi_server._camera_worker, 'request', Mock(return_value=b'frame'))
    readings = Mock(side_effect=[{'weight_g': w, 'calibrated': True} if isinstance(w, float) else w for w in
        [0.0, 0.0, 100.25, 100.25, -100.25, -100.25, UnstableScaleError('Scale moving; wait'), 350.0, 350.0]])
    monkeypatch.setattr(pi_server._scale_worker, 'request', readings)
    headers = _auth_header(officer_token)
    for expected in [0.0, 100.25, -100.25]:
        assert client.get('/api/hardware/weight', headers=headers).json()['weight_g'] is None
        response = client.get('/api/hardware/weight', headers=headers)
        assert response.status_code == 200
        assert response.json()['weight_g'] == expected
    unstable = client.get('/api/hardware/weight', headers=headers)
    assert unstable.status_code == 200
    assert unstable.json()['weight_g'] is None
    assert unstable.json()['measurement_state'] == 'unstable'
    assert unstable.json()['stable'] is False and unstable.json()['in_range'] is False
    assert client.get('/api/hardware/weight', headers=headers).json()['stable'] is False
    recovered = client.get('/api/hardware/weight', headers=headers).json()
    assert recovered['weight_g'] == 350 and recovered['stable'] and recovered['in_range']


def test_raw_samples_to_tare_api_and_saved_transaction(client, officer_token, farmer_id, pi_http, monkeypatch, tmp_path):
    """Use the real filter/offset math behind the actual Pi HTTP/backend routes."""
    from models.pending_transaction import PendingTransaction
    cfg = config()
    cfg.set('load_cell', 'CALIBRATION_FACTOR', '1000')
    monkeypatch.setattr(hx711_reader, 'CONFIG_PATH', str(tmp_path / 'config.ini'))
    hx711_reader.save_scale_config(cfg)
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'hardware')
    monkeypatch.setattr(pi_server._camera_worker, 'request', Mock(return_value=b'frame'))
    hx = Mock(_cgi_next_read_at=0.0)
    hx._read.side_effect = ([10000]*10 + [110000]*10 + [110000]*40 + [110000]*10
                           + [460000]*30 + [110000]*10 + [10000]*10
                           + [110000+i*100 for i in range(10)])
    def request(operation):
        if operation == 'tare':
            return hx711_reader.tare(hx)
        return hx711_reader.read_measurement(hx, hx711_reader._load_config())
    monkeypatch.setattr(pi_server._scale_worker, 'request', request)
    headers = _auth_header(officer_token)
    def weight():
        resp = client.get('/api/hardware/weight', headers=headers)
        assert resp.status_code == 200, resp.text
        return resp.json()
    assert weight()['weight_g'] is None  # Fresh but not yet temporally stable
    assert weight()['weight_g'] is None
    assert client.post('/api/hardware/weight', headers=headers, json={'action':'tare'}).status_code == 200
    assert weight()['weight_g'] is None  # Fresh but not yet temporally stable
    assert weight()['stable'] is False
    loaded = weight()
    assert loaded['weight_g'] == 350 and loaded['stable'] and loaded['in_range']
    initialized = client.post('/api/transaction/init', headers=headers, json={'farmer_id':farmer_id})
    assert initialized.status_code == 201
    pending_id = initialized.json()['pending_id']
    saved = client.put(f'/api/transaction/{pending_id}/weight', headers=headers, json={'weight_g':loaded['weight_g']})
    assert saved.status_code == 200
    with _TestSession() as db:
        assert float(db.get(PendingTransaction,pending_id).weight_g) == 350
    assert weight()['weight_g'] is None  # Fresh but not yet temporally stable
    assert weight()['weight_g'] is None
    noisy = weight()
    assert noisy['weight_g'] is None and noisy['measurement_state'] == 'unstable'
    assert not noisy['stable'] and not noisy['in_range']

@pytest.mark.parametrize('factor', [1000, -1000])
def test_website_weight_actions_through_http_and_raw_hx711(client, officer_token, pi_http,
                                                          monkeypatch, tmp_path, factor):
    """Real authenticated API and Pi HTTP; only ADC counts/camera are substituted."""
    from collections import deque
    path = tmp_path / 'scale.ini'
    cfg = config()
    cfg.remove_option('load_cell', 'CALIBRATION_VERIFIED')
    cfg.set('camera' if cfg.has_section('camera') else 'hardware', 'TEST_KEEP', 'preserved')
    monkeypatch.setattr(hx711_reader, 'CONFIG_PATH', str(path))
    hx711_reader.save_scale_config(cfg)
    before = path.read_bytes()
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'hardware')
    monkeypatch.setattr(pi_server, '_calibration', None)
    monkeypatch.setattr(pi_server, '_camera_readiness', lambda: 'ready')
    class ADC:
        raw = 10000
        def _read(self, **kwargs): return self.raw
    adc = ADC()
    def request(operation):
        cfg = hx711_reader._load_config()
        if operation == 'reference': return hx711_reader.collect_reference(adc, cfg)
        if operation == 'probe': return hx711_reader.filtered_sample(adc)
        if operation == 'tare': return hx711_reader.tare(adc)
        return hx711_reader.read_measurement(adc, cfg)
    monkeypatch.setattr(pi_server._scale_worker, 'request', request)
    headers = _auth_header(officer_token)
    def post(action, **extra):
        return client.post('/api/hardware/weight', headers=headers, json={'action':action, **extra})
    # Missing calibration must allow entering Weight, but cannot validate a sample.
    data = client.get('/api/hardware/weight', headers=headers).json()
    assert data['scale'] == 'ready' and data['weight_g'] is None and not data['in_range']
    zero = post('calibration_zero')
    assert zero.status_code == 200, zero.text
    token = zero.json()['token']
    assert post('calibration_finish', token=token).status_code == 503
    assert post('calibration_load', token='wrong', known_g=350).status_code == 503
    assert post('calibration_load', token=token, known_g=0).status_code == 422
    assert path.read_bytes() == before
    adc.raw = 10000 + factor * 350
    loaded = post('calibration_load', token=token, known_g=350)
    assert loaded.status_code == 200, loaded.text
    assert path.read_bytes() == before
    # Loaded platform is not a valid zero return; failed verification saves nothing.
    assert post('calibration_finish', token=token).status_code == 503
    assert path.read_bytes() == before
    adc.raw = 10000
    assert post('calibration_finish', token=token).json()['calibrated']
    saved = hx711_reader._load_config()  # Reopened from disk after calibration.
    assert saved.getfloat('load_cell', 'CALIBRATION_FACTOR') == factor
    assert saved.getfloat('load_cell', 'ZERO_OFFSET') == 10000
    assert saved.get('hardware', 'TEST_KEEP') == 'preserved'
    adc.raw = 10000 + factor * 100  # empty tray
    assert post('tare').json()['tared']
    for mass in (0, 339, 340, 350, 360, 361, -100):
        adc.raw = 10000 + factor * (100 + mass)
        client.get('/api/hardware/weight', headers=headers)
        data = client.get('/api/hardware/weight', headers=headers).json()
        assert data['weight_g'] == mass and data['stable']
        assert data['in_range'] == (340 <= mass <= 360)
    # Cancellation and expiry leave persisted settings intact.
    before = path.read_bytes()
    token = post('calibration_zero').json()['token']
    assert post('tare').status_code == 503
    assert post('calibration_cancel', token=token).json()['cancelled']
    token = post('calibration_zero').json()['token']
    pi_server._calibration['expires'] = 0
    assert post('calibration_load', token=token, known_g=350).status_code == 503
    assert path.read_bytes() == before


def test_browser_calibration_through_authenticated_api_and_pi_http(client, officer_token,
                                                                  pi_http, monkeypatch, tmp_path):
    """Chromium runs the actual Step 2 JS; raw ADC counts replace physical loads."""
    import json
    import re
    playwright = pytest.importorskip('playwright.sync_api')
    root = Path(__file__).resolve().parents[2]
    target = tmp_path / 'scale.ini'
    cfg = config()
    cfg.remove_option('load_cell', 'CALIBRATION_VERIFIED')
    monkeypatch.setattr(hx711_reader, 'CONFIG_PATH', str(target))
    hx711_reader.save_scale_config(cfg)
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'hardware')
    monkeypatch.setattr(pi_server, '_calibration', None)
    monkeypatch.setattr(pi_server, '_camera_readiness', lambda: 'ready')
    class ADC:
        raw = 10000
        def _read(self, **kwargs): return self.raw
    adc = ADC()
    def request(operation):
        cfg = hx711_reader._load_config()
        if operation == 'reference': return hx711_reader.collect_reference(adc, cfg)
        if operation == 'probe': return hx711_reader.filtered_sample(adc)
        if operation == 'tare': return hx711_reader.tare(adc)
        return hx711_reader.read_measurement(adc, cfg)
    monkeypatch.setattr(pi_server._scale_worker, 'request', request)
    html = re.sub(r'<\?.*?\?>', '', (root/'frontend/dashboard.php').read_text(), flags=re.S)
    html = re.sub(r'<script\b[^>]*>.*?</script>', '', html, flags=re.S)
    actions = []
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True,
                                     args=['--no-sandbox'])
        try:
            page = browser.new_page(viewport={'width':800, 'height':480})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            def route_request(route):
                from urllib.parse import urlsplit
                path = urlsplit(route.request.url).path
                if path == '/':
                    return route.fulfill(body=html, content_type='text/html')
                if path.startswith('/api/hardware/'):
                    if route.request.method == 'POST':
                        body = route.request.post_data_json
                        actions.append(body['action'])
                        response = client.post(path, json=body, headers=_auth_header(officer_token))
                    else:
                        response = client.get(path, headers=_auth_header(officer_token))
                    return route.fulfill(status=response.status_code, body=response.text,
                                         content_type='application/json')
                if route.request.method == 'DELETE' and path.endswith('/weight'):
                    return route.fulfill(json={'weight_g':None})
                if path == '/api/users/1/farmer':
                    return route.fulfill(json={'id':7, 'user_id':1})
                if path.endswith('/init'):
                    return route.fulfill(json={'pending_id':42, 'txn_number':'SCALE-TEST'})
                return route.abort()
            page.route('**/*', route_request)
            page.goto('http://cgi.test/')
            page.evaluate('''() => {
              for(let i=1;i<=6;i++){const e=document.createElement('span');e.id='step-badge-'+i;document.body.appendChild(e);}
              window.bootstrap={Modal:class {constructor(el){this.el=el} show(){} hide(){}}};
              window.CGI_API={del:path=>fetch(path,{method:'DELETE'}),get:path=>fetch(path),post:(path,body)=>fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})};
              document.getElementById('farmer-select').innerHTML='<option value="1">Test Farmer</option>';
            }''')
            page.add_script_tag(content=(root/'frontend/assets/js/dashboard.js').read_text())
            def click(id): page.locator('#'+id).evaluate('(e)=>e.click()')
            click('btn-start-txn')
            page.locator('.prep-check').evaluate_all('(els)=>els.forEach(e=>{e.checked=true;e.dispatchEvent(new Event("change"))})')
            page.wait_for_function("!document.getElementById('btn-to-weight').disabled")
            click('btn-to-weight')
            page.wait_for_function("!document.getElementById('stage-2').classList.contains('d-none')")
            def dialog_response(dialog):
                if dialog.type == 'prompt':
                    dialog.accept('350')
                else:
                    if dialog.message.startswith('Place ONLY'): adc.raw = 360000
                    if dialog.message.startswith('Remove the reference mass'): adc.raw = 10000
                    dialog.accept()
            page.on('dialog', dialog_response)
            click('btn-calibrate-scale')
            page.wait_for_function("!document.getElementById('btn-calibrate-scale').disabled")
            page.wait_for_function("document.getElementById('live-weight-value').textContent === '0.00 g'")
            assert actions == ['calibration_zero', 'calibration_load', 'calibration_finish']
            assert hx711_reader._load_config().getfloat('load_cell', 'CALIBRATION_FACTOR') == 1000
            adc.raw = 110000  # empty 100 g tray
            click('btn-tare-scale')
            page.wait_for_function("!document.getElementById('btn-tare-scale').disabled")
            assert hx711_reader._load_config().getfloat('load_cell', 'ZERO_OFFSET') == 110000
            adc.raw = 460000  # tray + 350 g sample
            page.wait_for_function("document.getElementById('live-weight-value').textContent === '350.00 g' && !document.getElementById('btn-to-capture').disabled")
            adc.raw = 471000  # tray + 361 g, rejected
            page.wait_for_function("document.getElementById('live-weight-value').textContent === '361.00 g' && document.getElementById('btn-to-capture').disabled")
            assert not errors, errors
        finally:
            browser.close()


def test_acquisition_negative_unstable_http_to_transaction(
        client, officer_token, farmer_id, pi_http, monkeypatch, caplog):
    from routers import transaction_workflow, hardware
    from models.pending_transaction import PendingTransaction
    cfg = config()
    cfg.set('load_cell', 'WEIGHT_TEST_MODE', 'true')
    cfg.set('load_cell', 'CALIBRATION_VERIFIED', 'true')
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'hardware')
    monkeypatch.setattr(pi_server, '_load_config', lambda: cfg)
    monkeypatch.setattr(pi_server, '_camera_readiness', lambda: 'ready')
    monkeypatch.setattr(pi_server._scale_worker, 'request', Mock(return_value={'raw_adc': 123345.6789, 'weight_g': -123.456789, 'calibrated': True}))
    monkeypatch.setattr(hardware.settings, 'WEIGHT_TEST_MODE', True)
    monkeypatch.setattr(transaction_workflow.settings, 'WEIGHT_TEST_MODE', True)
    headers = _auth_header(officer_token)
    first = client.get('/api/hardware/weight', headers=headers).json()
    assert first['weight_g'] is None and not first['valid_weight']
    reading = client.get('/api/hardware/weight', headers=headers).json()
    assert reading['weight_g'] == -123.456789
    assert reading['weight_test_mode'] and not reading['simulated']
    assert reading['stable'] and not reading['in_range']
    assert reading['measured_at']
    pending_id = client.post('/api/transaction/init', headers=headers,
                             json={'farmer_id': farmer_id}).json()['pending_id']
    saved = client.put(f'/api/transaction/{pending_id}/weight', headers=headers,
                       json={'weight_g': reading['weight_g'], 'measured_at': reading['measured_at']})
    assert saved.status_code == 422, saved.text
    with _TestSession() as db:
        assert db.get(PendingTransaction, pending_id).weight_g is None
    assert not reading['sample_present']
    assert not reading['weight_gate_passed']
    # A rejected negative reading was never recorded.  # Save acquired a newer reading.
    monkeypatch.setattr(pi_server._scale_worker, 'request', Mock(side_effect=RuntimeError('Disconnected')))
    assert client.get('/api/hardware/weight', headers=headers).status_code == 503
    assert client.get('/api/hardware/status', headers=headers).json()['scale'] == 'error'
    monkeypatch.setattr(transaction_workflow.settings, 'WEIGHT_TEST_MODE', False)
    assert client.put(f'/api/transaction/{pending_id}/weight', headers=headers,
                      json={'weight_g': -123.456789}).status_code == 422


def test_uncalibrated_million_counts_through_authenticated_proxy(client, officer_token, pi_http, monkeypatch):
    cfg = config()
    cfg.set('load_cell', 'WEIGHT_TEST_MODE', 'true')
    cfg.set('load_cell', 'CALIBRATION_VERIFIED', 'false')
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'hardware')
    monkeypatch.setattr(pi_server, '_load_config', lambda: cfg)
    monkeypatch.setattr(pi_server, '_camera_readiness', lambda: 'ready')
    adc = Mock(_cgi_next_read_at=0.0)
    adc._read.side_effect = [1000000, 1100000, 1000005]
    monkeypatch.setattr(pi_server._scale_worker, 'request',
                        lambda operation: hx711_reader.read_measurement(adc, cfg))
    for raw in [1000000, 1100000, 1000005]:
        response = client.get('/api/hardware/weight', headers=_auth_header(officer_token))
        assert response.status_code == 200
        data = response.json()
        assert data['raw_adc'] == raw and data['raw_unit'] == 'ADC counts'
        assert data['weight_g'] is None and not data['calibrated']
        assert not data['stable'] and not data['in_range']

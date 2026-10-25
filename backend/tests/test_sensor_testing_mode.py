"""Stage 2 acquisition testing; software cases mock ADC/Pi, optional live case reads HX711."""
import configparser
import json
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock
import pytest
import hx711_reader as scale
from services import scale_measurement
from routers import hardware, transaction_workflow as workflow
from tests.test_integration import client, admin_token, officer_token, farmer_id, _auth_header, _TestSession
from models.pending_transaction import PendingTransaction


@pytest.fixture(autouse=True)
def mode(monkeypatch):
    monkeypatch.setattr(workflow.settings, 'WEIGHT_SENSOR_TEST_MODE', True)
    monkeypatch.setattr(scale_measurement, '_latest_sensor_reading', None)


def payload(value, calibrated=False):
    return dict(scale='ready', simulated=False, calibrated=calibrated, stable=False,
                raw_counts=value, weight_g=value if calibrated else None,
                measured_at=datetime.now(timezone.utc).isoformat())


@pytest.mark.parametrize('value', [-500,0,9999.9,100000,1000000,7164226])
@pytest.mark.parametrize('calibrated', [False,True])
def test_any_finite_reading_reaches_capture(client, officer_token, farmer_id, monkeypatch, value, calibrated):
    data = payload(value, calibrated)
    monkeypatch.setattr(hardware, '_pi_get', AsyncMock(return_value=data))
    monkeypatch.setattr(workflow, '_pi_get', AsyncMock(return_value=data))
    headers = _auth_header(officer_token)
    live = client.get('/api/hardware/weight', headers=headers).json()
    assert live['weight_gate_passed'] and live['sensor_reading']['value'] == value
    pid = client.post('/api/transaction/init', headers=headers, json={'farmer_id':farmer_id}).json()['pending_id']
    response = client.put(f'/api/transaction/{pid}/weight', headers=headers,
                          json={'weight_g':350, 'sensor_test_mode':False})
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'weighed'
    saved = json.loads(response.json()['weight_metadata'])['sensor_reading']
    assert saved['value'] == value and saved['unit'] == ('g' if calibrated else 'ADC counts')
    with _TestSession() as db:
        assert db.get(PendingTransaction,pid).weight_g is None
    # Existing analysis gate cannot interpret diagnostics as grams.
    from tests.test_integration import _tiny_jpeg_b64
    with monkeypatch.context() as normal:
        normal.setattr(workflow.settings, 'WEIGHT_SENSOR_TEST_MODE', False)
        assert client.post('/api/inspection/capture-dual', headers=headers, json={
            'pending_id':pid,'image_a_b64':_tiny_jpeg_b64(),'image_b_b64':_tiny_jpeg_b64()}).status_code == 422


def test_disconnected_can_continue_without_fake_reading(client, officer_token, farmer_id, monkeypatch):
    monkeypatch.setattr(workflow, '_pi_get', AsyncMock(side_effect=TimeoutError()))
    headers = _auth_header(officer_token)
    pid = client.post('/api/transaction/init', headers=headers, json={'farmer_id':farmer_id}).json()['pending_id']
    response = client.put(f'/api/transaction/{pid}/weight', headers=headers, json={})
    assert response.status_code == 200
    metadata = json.loads(response.json()['weight_metadata'])
    assert metadata['sensor_reading'] is None and metadata['scale_status_at_confirmation'] == 'error'


def test_single_raw_conversion_without_stability_or_calibration():
    cfg = configparser.ConfigParser()
    cfg.read_dict({'load_cell':{'WEIGHT_SENSOR_TEST_MODE':'true'}})
    class ADC:
        def _read(self, **kwargs): return -1000000
    result = scale.read_measurement(ADC(), cfg)
    assert result['raw_counts'] == -1000000 and result['weight_g'] is None


def test_failed_read_preserves_last_diagnostic_with_its_timestamp():
    first = scale_measurement.sensor_testing_status(payload(-500))
    failed = scale_measurement.sensor_testing_status({'scale':'error'})
    assert failed.get('sensor_reading') is None
    assert failed['latest_sensor_reading'] == first['sensor_reading']


@pytest.mark.skipif(os.getenv('LIVE_HX711_TEST') != '1', reason='Explicit live hardware check only')
def test_real_pi_to_authenticated_backend_and_pending_transaction(client, officer_token, farmer_id):
    headers = _auth_header(officer_token)
    observations = [client.get('/api/hardware/weight', headers=headers).json() for _ in range(3)]
    for data in observations:
        assert data['sensor_test_mode'] and data['simulated'] is False
        print('LIVE HX711:', data.get('sensor_reading') or {'scale':data['scale'],'error':data.get('error')})
        if data['scale'] != 'ready': assert not data.get('sensor_reading')
    pid = client.post('/api/transaction/init', headers=headers, json={'farmer_id':farmer_id}).json()['pending_id']
    response = client.put(f'/api/transaction/{pid}/weight', headers=headers, json={})
    assert response.status_code == 200, response.text
    print('LIVE pending acceptance:', response.json()['weight_metadata'])
    assert response.json()['weight_g'] is None
    assert 'sensor_reading' in json.loads(response.json()['weight_metadata'])

    # Actual browser JS -> authenticated backend -> physical Pi; database remains isolated.
    import re
    from pathlib import Path
    from urllib.parse import urlsplit
    playwright = pytest.importorskip('playwright.sync_api')
    root = Path(__file__).resolve().parents[2]
    html = re.sub(r'<\?.*?\?>', '', (root/'frontend/dashboard.php').read_text(), flags=re.S)
    html = re.sub(r'<script\b[^>]*>.*?</script>', '', html, flags=re.S)
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
        try:
            page = browser.new_page(viewport={'width':800,'height':480})
            errors, saved = [], []
            page.on('pageerror', lambda error:errors.append(str(error)))
            def route_request(route):
                path = urlsplit(route.request.url).path
                if path == '/': return route.fulfill(body=html, content_type='text/html')
                # Prepare checks and preview are scaffolding; Stage 2 acquisition/acceptance are real.
                if path == '/api/hardware/status':
                    return route.fulfill(json={'camera':'ready','scale':'ready','printer':'warning','sensor_test_mode':True})
                if path == '/api/users/1/farmer': return route.fulfill(json={'id':farmer_id,'user_id':1})
                if path == '/api/hardware/capture': return route.fulfill(status=503,json={'detail':'Camera preview excluded from sensor test'})
                if path.startswith('/api/'):
                    request = route.request
                    result = client.request(request.method,path,headers=headers,
                        **({'json':request.post_data_json} if request.post_data else {}))
                    print('LIVE browser API:', request.method, path, result.status_code)
                    if request.method == 'PUT' and path.endswith('/weight'): saved.append(result.json())
                    return route.fulfill(status=result.status_code,body=result.text,content_type='application/json')
                return route.abort()
            page.route('**/*',route_request)
            page.goto('http://cgi.test/')
            page.evaluate('''() => {
              for(let i=1;i<=6;i++){const el=document.createElement('span');el.id='step-badge-'+i;document.body.appendChild(el);}
              window.bootstrap={Modal:class {show(){} hide(){}}};
              window.CGI_API={get:p=>fetch(p),post:(p,b)=>fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}),put:(p,b)=>fetch(p,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})};
              document.getElementById('farmer-select').innerHTML='<option value="1">Test Farmer</option>';
            }''')
            page.add_script_tag(content=(root/'frontend/assets/js/dashboard.js').read_text())
            def click(id):page.locator('#'+id).evaluate('(el)=>el.click()')
            click('btn-start-txn')
            page.locator('.prep-check').evaluate_all('(els)=>els.forEach(el=>{el.checked=true;el.dispatchEvent(new Event("change"))})')
            page.wait_for_function("!document.getElementById('btn-to-weight').disabled")
            click('btn-to-weight')
            try:
                page.wait_for_function("!document.getElementById('stage-2').classList.contains('d-none')")
                page.wait_for_function("document.getElementById('weight-range-bypass').textContent.includes('Sensor testing')")
            except Exception:
                print('Browser diagnostics:', errors, page.locator('#stage1-error').text_content(), page.locator('#weight-status-badge').text_content())
                raise
            print('LIVE browser display:',page.locator('#live-weight-value').inner_text())
            assert not page.locator('#btn-to-capture').is_disabled()
            click('btn-to-capture')
            page.wait_for_function("!document.getElementById('stage-3').classList.contains('d-none')")
            assert saved and saved[-1]['weight_g'] is None
            print('LIVE browser Stage 3 acceptance:',saved[-1]['weight_metadata'])
            assert not errors,errors
        finally:
            browser.close()


@pytest.mark.parametrize('scenario', ['inference','missing_model','inference_error','unprepared'])
def test_sensor_image_analysis_without_sale(client, officer_token, farmer_id, monkeypatch, tmp_path, scenario):
    from unittest.mock import Mock
    from routers import inspection
    from services import pricing
    from models.inspection import Inspection
    from models.transaction import Transaction
    from tests.test_integration import _tiny_jpeg_b64
    monkeypatch.setattr(inspection.settings, 'UPLOAD_DIR', str(tmp_path))
    monkeypatch.setattr(inspection.settings, 'YOLO_MODEL_PATH', str(tmp_path/'model.pt'))
    monkeypatch.setattr(inspection.settings, 'YOLO_ALLOW_MISSING_MODEL', scenario == 'missing_model')
    detect = Mock(side_effect=RuntimeError('Inference failed')) if scenario == 'inference_error' else Mock(
        return_value=({'total_beans':100, 'class_counts':{'black_bean':2}}, b'annotated-image'))
    monkeypatch.setattr(inspection, 'run_detection_with_annotation', detect)
    price = AsyncMock(side_effect=AssertionError('Sensor test must not invoke pricing'))
    monkeypatch.setattr(pricing, 'suggest_price', price)
    monkeypatch.setattr(workflow, '_pi_get', AsyncMock(return_value=payload(1234567)))
    headers = _auth_header(officer_token)
    pid = client.post('/api/transaction/init',headers=headers,json={'farmer_id':farmer_id}).json()['pending_id']
    if scenario != 'unprepared':
        assert client.put(f'/api/transaction/{pid}/weight',headers=headers,json={}).status_code == 200
    with _TestSession() as db:
        before = db.query(Inspection).count(),db.query(Transaction).count()
    response = client.post('/api/inspection/capture-dual',headers=headers,json={
        'pending_id':pid,'image_a_b64':_tiny_jpeg_b64(),'image_b_b64':_tiny_jpeg_b64()})
    assert response.status_code == (422 if scenario == 'unprepared' else 500 if scenario == 'inference_error' else 201), response.text
    price.assert_not_called()
    with _TestSession() as db:
        assert (db.query(Inspection).count(),db.query(Transaction).count()) == before
        row = db.get(PendingTransaction,pid)
        assert row.weight_g is None
        if scenario == 'inference':
            result = response.json()
            assert result['sensor_test_mode'] and not result['analysis_skipped']
            assert result['grade'] == 'extra_class' and result['total_beans_detected'] == 100
            assert result['pricing_unavailable'] and result['sample_weight_g'] is None and result['txn_id'] is None
            assert result['total_price'] is None and result['price_per_kg'] is None
            assert result['sensor_reading']['unit'] == 'ADC counts'
            assert detect.call_count == 2
            saved = json.loads(row.weight_metadata)['sensor_analysis']
            assert saved == result
            assert (tmp_path/result['image_path_annotated_a'].split('/')[-1]).exists()
            assert client.put(f'/api/transaction/{pid}/weight',headers=headers,json={}).status_code == 409
        elif scenario == 'missing_model':
            result = response.json()
            assert result['analysis_skipped'] and result['sample_weight_g'] is None
            assert result['sensor_reading']['value'] == 1234567
            detect.assert_not_called()
        else:
            assert not list(tmp_path.glob('*.jpg'))

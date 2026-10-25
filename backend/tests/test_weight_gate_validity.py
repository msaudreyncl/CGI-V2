"""Software checks only: mocked ADC and Pi payloads, no physical accuracy claim."""
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, Mock
import pytest
from services.scale_measurement import measurement_status
from tests.test_integration import client, admin_token, officer_token, farmer_id, _auth_header, _TestSession
from models.pending_transaction import PendingTransaction


def reading(weight=125, **changes):
    result = dict(weight_g=weight, raw_counts=1000000, calibrated=True,
                  simulated=False, scale='ready', stable=True, weight_test_mode=True,
                  measured_at=datetime.now(timezone.utc).isoformat())
    result.update(changes)
    return result


@pytest.mark.parametrize('weight,normal', [(125,False),(339.99,False),(340,True),
                                         (350,True),(360,True),(360.01,False),(400,False)])
@pytest.mark.parametrize('bypass',[False,True])
def test_range_only(weight, normal, bypass):
    result = measurement_status(reading(weight), bypass)
    assert result['weight_g'] == weight
    assert result['weight_gate_passed'] == (bypass or normal)


@pytest.mark.parametrize('changes', [dict(calibrated=False),dict(scale='error'),
    dict(stable=False),dict(weight_g=None),dict(weight_g=float('nan')),
    dict(weight_g=float('inf')),dict(simulated=True),dict(measured_at=None),
    dict(measured_at=(datetime.now(timezone.utc)-timedelta(seconds=11)).isoformat())])
def test_invalid_never_bypasses(changes):
    result = measurement_status(reading(**changes), True)
    assert not result['weight_gate_passed'] and result['weight_g'] is None


def test_endpoint_rechecks_scale_and_saves_actual(client, officer_token, farmer_id, monkeypatch, tmp_path):
    from routers import transaction_workflow as workflow
    monkeypatch.setattr(workflow.settings, 'WEIGHT_TEST_MODE', True)
    probe = AsyncMock(return_value=reading())
    monkeypatch.setattr(workflow, '_pi_get', probe)
    headers = _auth_header(officer_token)
    pid = client.post('/api/transaction/init', headers=headers,
                      json={'farmer_id':farmer_id}).json()['pending_id']
    url = f'/api/transaction/{pid}/weight'
    response = client.put(url, headers=headers, json={'weight_g':350})
    assert response.status_code == 200, response.text
    with _TestSession() as db:
        assert float(db.get(PendingTransaction, pid).weight_g) == 125
    # Carry actual grams through analysis, pricing and transaction completion.
    from routers import inspection
    from services import pricing
    from tests.test_integration import _tiny_jpeg_b64
    monkeypatch.setattr(inspection.settings, 'UPLOAD_DIR', str(tmp_path))
    monkeypatch.setattr(inspection.settings, 'YOLO_ALLOW_MISSING_MODEL', False)
    monkeypatch.setattr(inspection, 'run_detection_with_annotation', Mock(return_value=(
        {'total_beans':100,'class_counts':{'black_bean':2}}, b'')))
    monkeypatch.setattr(pricing, 'suggest_price', AsyncMock(return_value={
        'price_per_kg':200, 'market_rate_per_kg':250, 'multiplier':.8,
        'currency':'PHP', 'source':'manual'}))
    analyzed = client.post('/api/inspection/capture-dual', headers=headers, json={
        'pending_id':pid,'image_a_b64':_tiny_jpeg_b64(),'image_b_b64':_tiny_jpeg_b64()})
    assert analyzed.status_code == 201, analyzed.text
    assert analyzed.json()['sample_weight_g'] == 125
    tid = analyzed.json()['txn_id']
    import json
    from models.inspection import Inspection
    from models.transaction import Transaction
    from services.thermal_print import print_receipt
    import importlib
    printer_module = importlib.import_module("escpos.printer")
    printer = Mock()
    monkeypatch.setattr(printer_module, 'Network', Mock(return_value=printer))
    monkeypatch.setattr(printer_module, 'Usb', Mock(return_value=printer))
    with _TestSession() as db:
        record = db.get(Inspection, analyzed.json()['id'])
        assert json.loads(record.notes)['weight_range_bypass_used'] is True
        print_receipt(db.get(Transaction, tid), db)
    assert any('0.125 kg' in str(call) for call in printer.text.call_args_list)
    history = client.get('/api/transactions', headers=headers).json()
    assert next(row for row in history if row['id'] == tid)['weight_kg'] == .125
    # Live polling cannot change accepted transaction grams.
    monkeypatch.setattr(workflow, '_pi_get', AsyncMock(return_value=reading(400)))
    with _TestSession() as db:
        assert float(db.get(PendingTransaction, pid).weight_g) == 125
    monkeypatch.setattr(workflow, '_pi_get', probe)
    completed = client.put(f'/api/transactions/{tid}', headers=headers, json={'status':'completed'})
    assert completed.status_code == 200, completed.text
    assert completed.json()['weight_kg'] == .125
    assert completed.json()['total_price'] == 25
    assert client.put(url, headers=headers, json={'weight_g':350}).status_code == 409
    assert client.delete(url, headers=headers).status_code == 409
    assert client.post('/api/inspection/capture-dual', headers=headers, json={
        'pending_id':pid,'image_a_b64':_tiny_jpeg_b64(),'image_b_b64':_tiny_jpeg_b64()}).status_code == 409
    pid = client.post('/api/transaction/init', headers=headers,
                      json={'farmer_id':farmer_id}).json()['pending_id']
    url = f'/api/transaction/{pid}/weight'
    for changes in [dict(calibrated=False),dict(stable=False),dict(scale='error'),
                    dict(measured_at='2000-01-01T00:00:00+00:00')]:
        probe.return_value = reading(**changes)
        assert client.put(url, headers=headers, json={'weight_g':350}).status_code == 422
    probe.return_value = reading()
    monkeypatch.setattr(workflow.settings, 'WEIGHT_TEST_MODE', False)
    assert client.put(url, headers=headers, json={'weight_g':350}).status_code == 422
    probe.side_effect = TimeoutError()
    assert client.put(url, headers=headers, json={'weight_g':350}).status_code == 503


def test_explicit_instability_is_not_mislabeled_as_communication_failure():
    result = measurement_status(reading(weight_g=None, calibrated=False,
        measurement_state='unstable', stable=False, measured_at=None), True)
    assert result['status_message'] == 'Scale unstable'
    assert not result['weight_gate_passed']


@pytest.mark.parametrize('weight', [-125, 0, 0.01, 0.5, 1.0])
def test_empty_noise_and_negative_cannot_bypass(weight):
    result = measurement_status(reading(weight), True)
    assert result['weight_g'] == weight  # calibrated signed grams remain honest
    assert not result['sample_present'] and not result['weight_gate_passed']


def test_configured_noise_floor():
    assert not measurement_status(reading(2, sample_noise_floor_g=3), True)['weight_gate_passed']
    assert measurement_status(reading(4, sample_noise_floor_g=3), True)['weight_gate_passed']


def test_tare_and_return_invalidate_pending_acceptance(client, officer_token, farmer_id, monkeypatch):
    import json
    from routers import transaction_workflow as workflow, hardware
    from models.pending_transaction import PendingStatus
    monkeypatch.setattr(workflow.settings, 'WEIGHT_TEST_MODE', True)
    monkeypatch.setattr(workflow, '_pi_get', AsyncMock(return_value=reading()))
    monkeypatch.setattr(hardware, '_pi_post', AsyncMock(return_value={'tared':True}))
    headers = _auth_header(officer_token)
    pid = client.post('/api/transaction/init', headers=headers,
                      json={'farmer_id':farmer_id}).json()['pending_id']
    url = f'/api/transaction/{pid}/weight'
    assert client.put(url, headers=headers, json={'weight_g':350,'bypass':False}).status_code == 200
    with _TestSession() as db:
        row = db.get(PendingTransaction, pid)
        assert json.loads(row.weight_metadata)['weight_range_bypass_used'] is True
    assert client.delete(url, headers=headers).json()['weight_g'] is None
    assert client.put(url, headers=headers, json={'weight_g':350}).status_code == 200
    assert client.post('/api/hardware/weight', headers=headers, json={'action':'tare'}).status_code == 200
    with _TestSession() as db:
        row = db.get(PendingTransaction, pid)
        assert row.weight_g is None and row.weight_metadata is None
        assert row.status == PendingStatus.prepared

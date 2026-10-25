"""Completion archive tests use only the isolated temporary SQLite integration DB."""
import json
from unittest.mock import AsyncMock, Mock

import pytest
from tests.test_integration import (
    client, admin_token, officer_token, farmer_id, _auth_header,
    _TestSession, _tiny_jpeg_b64,
)
from models.pending_transaction import PendingTransaction, PendingStatus
from models.inspection import Inspection
from models.transaction import Transaction
from routers import transaction_workflow as workflow, inspection


@pytest.mark.parametrize('value', [-500, 0, 1000000, 7164226, None])
@pytest.mark.parametrize('calibrated', [False, True])
@pytest.mark.parametrize('missing_model', [False, True])
def test_finish_preserves_real_readings_without_sale(
        client, officer_token, farmer_id, monkeypatch, tmp_path, value, calibrated, missing_model):
    from services import pricing, scale_measurement
    monkeypatch.setattr(workflow.settings, 'WEIGHT_SENSOR_TEST_MODE', True)
    monkeypatch.setattr(scale_measurement, '_latest_sensor_reading', None)
    monkeypatch.setattr(inspection.settings, 'YOLO_ALLOW_MISSING_MODEL', missing_model)
    monkeypatch.setattr(inspection.settings, 'YOLO_MODEL_PATH', str(tmp_path/'missing.pt'))
    monkeypatch.setattr(inspection.settings, 'UPLOAD_DIR', str(tmp_path))
    data = dict(scale='ready' if value is not None else 'error', simulated=False,
                raw_counts=value, weight_g=value if calibrated else None, calibrated=calibrated,
                measured_at='2026-10-25T12:00:00+00:00')
    monkeypatch.setattr(workflow, '_pi_get', AsyncMock(return_value=data))
    # Intentionally poor/inaccurate detection must still retain exactly the generated result.
    detect = Mock(return_value=({'total_beans': 10, 'class_counts': {'black_bean': 99}}, None))
    monkeypatch.setattr(inspection, 'run_detection_with_annotation', detect)
    price = AsyncMock(side_effect=AssertionError('Sensor archive must not invoke pricing'))
    monkeypatch.setattr(pricing, 'suggest_price', price)
    headers = _auth_header(officer_token)
    with _TestSession() as db:
        counts = db.query(Inspection).count(), db.query(Transaction).count()
    pid = client.post('/api/transaction/init', headers=headers, json={'farmer_id': farmer_id}).json()['pending_id']
    assert client.put(f'/api/transaction/{pid}/weight', headers=headers, json={}).status_code == 200
    analyzed = client.post('/api/inspection/capture-dual', headers=headers, json={
        'pending_id': pid, 'image_a_b64': _tiny_jpeg_b64(), 'image_b_b64': _tiny_jpeg_b64()})
    assert analyzed.status_code == 201, analyzed.text
    result = analyzed.json()
    endpoint = f'/api/transaction/{pid}/complete-test'
    first = client.put(endpoint, headers=headers, json={})
    assert first.status_code == 200, first.text
    assert first.json()['status'] == 'completed'
    assert client.put(endpoint, headers=headers, json={}).json() == first.json()
    with _TestSession() as db:
        pending = db.get(PendingTransaction, pid)
        metadata = json.loads(pending.weight_metadata)
        assert pending.weight_g is None
        assert (db.query(Inspection).count(), db.query(Transaction).count()) == counts
        reading = metadata['sensor_reading']
        if value is None:
            assert reading is None
        else:
            assert reading['value'] == value
            assert reading['raw_counts'] == value
            assert reading['unit'] == ('g' if calibrated else 'ADC counts')
        if missing_model:
            assert 'sensor_analysis' not in metadata
            assert metadata['capture_result']['image_path'] == result['image_path']
        else:
            assert metadata['sensor_analysis'] == result
            assert result['grade'] == 'class_ii'
            assert result['defect_results'][0]['bean_count'] == 99
            assert result['total_price'] is None
    # New authenticated session reads the durable record, without relying on browser state.
    login = client.post('/api/auth/login', json={'email':'officer@test.local','password':'Officer@1234'})
    fresh = _auth_header(login.json()['access_token'])
    all_rows = client.get('/api/transaction/completed-tests?limit=100', headers=fresh)
    assert all_rows.status_code == 200
    assert [r['id'] for r in all_rows.json()].count(pid) == 1
    assert next(r for r in all_rows.json() if r['id'] == pid) == first.json()
    # A refresh cannot re-run capture or alter a finished reading.
    assert client.put(f'/api/transaction/{pid}/weight', headers=headers, json={}).status_code == 409
    price.assert_not_called()
    assert detect.call_count == (0 if missing_model else 2)


def test_unfinished_and_unauthorized_runs_cannot_be_finished(client, officer_token, farmer_id):
    headers = _auth_header(officer_token)
    pid = client.post('/api/transaction/init', headers=headers, json={'farmer_id': farmer_id}).json()['pending_id']
    assert client.put(f'/api/transaction/{pid}/complete-test', headers=headers, json={}).status_code == 409
    assert client.put(f'/api/transaction/{pid}/complete-test', json={}).status_code in (401, 403)
    assert client.put('/api/transaction/999999/complete-test', headers=headers, json={}).status_code == 404
    assert client.get('/api/transaction/completed-tests').status_code in (401,403)


def test_simulation_is_archived_once_and_explicitly_labelled(client, officer_token, farmer_id):
    headers = _auth_header(officer_token)
    payload = {'farmer_id': farmer_id, 'txn_number':'DEV-20261026-ABC123',
               'result':{'sample_weight_g':-500, 'grade':None, 'total_beans_detected':None,
                         'total_price':None, 'defect_results':[]}}
    with _TestSession() as db:
        before = db.query(PendingTransaction).count()
    first = client.post('/api/transaction/complete-simulation', headers=headers, json=payload)
    assert first.status_code == 200, first.text
    assert client.post('/api/transaction/complete-simulation', headers=headers, json=payload).json() == first.json()
    metadata = json.loads(first.json()['weight_metadata'])
    assert metadata['simulated'] is True and metadata['simulation_result'] == payload['result']
    assert first.json()['weight_g'] is None
    with _TestSession() as db:
        assert db.query(PendingTransaction).count() == before + 1
    rows = client.get('/api/transaction/completed-tests', headers=headers).json()
    assert sum(r['id']==first.json()['id'] for r in rows)==1


def test_normal_sale_completion_path_remains_separate(client, officer_token, farmer_id, monkeypatch, tmp_path):
    from services import pricing
    monkeypatch.setattr(workflow.settings, 'WEIGHT_SENSOR_TEST_MODE', False)
    monkeypatch.setattr(workflow.settings, 'YOLO_ALLOW_MISSING_MODEL', False)
    monkeypatch.setattr(inspection.settings, 'UPLOAD_DIR', str(tmp_path))
    monkeypatch.setattr(workflow, 'measurement_status', lambda *a:dict(
        weight_gate_passed=True, weight_g=350, measured_at='2026-10-25T12:00:00+00:00', bypass_weight_range=False))
    monkeypatch.setattr(workflow, '_pi_get', AsyncMock(return_value={}))
    monkeypatch.setattr(inspection,'run_detection_with_annotation',Mock(return_value=(
        {'total_beans':100,'class_counts':{'black_bean':2}},None)))
    monkeypatch.setattr(pricing,'suggest_price',AsyncMock(return_value={
        'price_per_kg':190,'market_rate_per_kg':200,'multiplier':.95,'total_price':66.5,
        'currency':'PHP','source':'manual'}))
    headers=_auth_header(officer_token)
    pid=client.post('/api/transaction/init',headers=headers,json={'farmer_id':farmer_id}).json()['pending_id']
    assert client.put(f'/api/transaction/{pid}/weight',headers=headers,json={}).status_code==200
    response=client.post('/api/inspection/capture-dual',headers=headers,json={
        'pending_id':pid,'image_a_b64':_tiny_jpeg_b64(),'image_b_b64':_tiny_jpeg_b64()})
    assert response.status_code==201,response.text
    result=response.json()
    assert result['sample_weight_g']==350 and result['total_price']==66.5 and result['grade']=='extra_class'
    assert client.put(f'/api/transaction/{pid}/complete-test',headers=headers,json={}).status_code==409
    txn_id=result['txn_id']
    first=client.put(f'/api/transactions/{txn_id}',headers=headers,json={'status':'completed'})
    assert first.status_code==200 and first.json()['total_price']==66.5
    assert client.put(f'/api/transactions/{txn_id}',headers=headers,json={'status':'completed'}).status_code==200
    assert all(r['id']!=pid for r in client.get('/api/transaction/completed-tests',headers=headers).json())
    with _TestSession() as db:
        assert db.query(Transaction).filter(Transaction.id==txn_id).count()==1


def test_history_respects_farmer_visibility_and_completion_ownership(client, officer_token, admin_token, farmer_id):
    officer = _auth_header(officer_token)
    admin = _auth_header(admin_token)
    # Another officer's pending row cannot be completed by this officer.
    pid = client.post('/api/transaction/init', headers=admin, json={'farmer_id':farmer_id}).json()['pending_id']
    with _TestSession() as db:
        pending = db.get(PendingTransaction,pid)
        pending.status=PendingStatus.captured
        db.commit()
    assert client.put(f'/api/transaction/{pid}/complete-test',headers=officer,json={}).status_code==403
    assert client.put(f'/api/transaction/{pid}/complete-test',headers=admin,json={}).status_code==200
    farmer_login=client.post('/api/auth/login',json={'email':'farmer@test.local','password':'Farmer@1234'})
    farmer=_auth_header(farmer_login.json()['access_token'])
    rows=client.get('/api/transaction/completed-tests',headers=farmer).json()
    assert rows and all(row['farmer_id']==farmer_id for row in rows)
    assert client.put(f'/api/transaction/{pid}/complete-test',headers=farmer,json={}).status_code==403
    new_farmer=client.post('/api/auth/register',headers=admin,json={
        'name':'Other Farmer','email':'other-farmer@test.local','password':'Farmer@1234','role':'farmer'})
    assert new_farmer.status_code==201
    login=client.post('/api/auth/login',json={'email':'other-farmer@test.local','password':'Farmer@1234'})
    assert client.get('/api/transaction/completed-tests',headers=_auth_header(login.json()['access_token'])).json()==[]


def test_history_pagination_does_not_duplicate_completed_runs(client, officer_token):
    headers=_auth_header(officer_token)
    all_rows=client.get('/api/transaction/completed-tests?limit=100',headers=headers).json()
    paged=[]
    for skip in range(0,len(all_rows),3):
        page=client.get(f'/api/transaction/completed-tests?skip={skip}&limit=3',headers=headers)
        assert page.status_code==200
        paged.extend(page.json())
    assert [r['id'] for r in paged]==[r['id'] for r in all_rows]
    assert len({r['id'] for r in paged})==len(paged)

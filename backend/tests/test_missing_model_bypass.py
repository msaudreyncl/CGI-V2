"""Missing-model testing must never manufacture a grade or finalized sale."""
from unittest.mock import Mock
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_integration import client, admin_token, officer_token, farmer_id, _TestSession, _auth_header


def test_missing_model_bypass_retains_capture_without_grading(
        client, officer_token, farmer_id, monkeypatch, tmp_path):
    from routers import inspection
    from models.inspection import Inspection
    from models.transaction import Transaction
    from models.pending_transaction import PendingTransaction, PendingStatus
    monkeypatch.setattr(inspection.settings, 'YOLO_MODEL_PATH', str(tmp_path / 'missing.pt'))
    monkeypatch.setattr(inspection.settings, 'YOLO_ALLOW_MISSING_MODEL', True)
    monkeypatch.setattr(inspection.settings, 'UPLOAD_DIR', str(tmp_path))
    detect = Mock(side_effect=RuntimeError('Must not run inference'))
    monkeypatch.setattr(inspection, 'run_detection_with_annotation', detect)
    headers = _auth_header(officer_token)
    pending_id = client.post('/api/transaction/init', headers=headers,
                             json={'farmer_id': farmer_id}).json()['pending_id']
    assert client.put(f'/api/transaction/{pending_id}/weight', headers=headers,
                      json={'weight_g': 350}).status_code == 200
    with _TestSession() as db:
        before = (db.query(Inspection).count(), db.query(Transaction).count())
    payload = {'pending_id': pending_id, 'image_a_b64': 'YWJj', 'image_b_b64': 'ZGVm'}
    response = client.post('/api/inspection/capture-dual', headers=headers, json=payload)
    assert response.status_code == 201, response.text
    result = response.json()
    assert result['analysis_skipped'] and result['grade'] is None and result['txn_id'] is None
    assert result['total_beans_detected'] is None and result['defect_results'] == []
    assert result['sample_weight_g'] == 350
    assert (tmp_path / result['image_path'].split('/')[-1]).read_bytes() == b'abc'
    assert (tmp_path / result['image_path_b'].split('/')[-1]).read_bytes() == b'def'
    with _TestSession() as db:
        pending = db.get(PendingTransaction, pending_id)
        assert pending.status == PendingStatus.captured
        assert result['txn_number'] == pending.txn_number
        assert (db.query(Inspection).count(), db.query(Transaction).count()) == before
    detect.assert_not_called()
    # A present model must use real inference; inference failures are not bypassed.
    model = tmp_path / 'missing.pt'
    model.touch()
    assert client.post('/api/inspection/capture-dual', headers=headers, json=payload).status_code == 500
    model.unlink()
    monkeypatch.setattr(inspection.settings, 'YOLO_ALLOW_MISSING_MODEL', False)
    assert client.post('/api/inspection/capture-dual', headers=headers, json=payload).status_code == 500

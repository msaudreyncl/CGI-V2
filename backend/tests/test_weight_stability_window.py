"""Software-only timing tests; no GPIO or hardware accuracy claim."""
import configparser
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
import pi_server


@pytest.fixture
def scale_clock(monkeypatch):
    cfg = configparser.ConfigParser()
    cfg.read_dict({'load_cell': {'STABILITY_DURATION_S':'1', 'MAX_SPREAD_G':'.5',
                                'UNSTABLE_AFTER_S':'3', 'SAMPLE_NOISE_FLOOR_G':'2'}})
    clock = [0.0]
    worker = Mock(return_value={'weight_g':125., 'calibrated':True})
    monkeypatch.setattr(pi_server, '_load_config', lambda:cfg)
    monkeypatch.setattr(pi_server, 'simulated', lambda cfg:False)
    monkeypatch.setattr(pi_server, 'time', SimpleNamespace(monotonic=lambda:clock[0]))
    monkeypatch.setattr(pi_server._scale_worker, 'request', worker)
    monkeypatch.setattr(pi_server, '_calibration', None)
    monkeypatch.setattr(pi_server, '_last_weight', None)
    return clock, worker


def test_duration_not_two_quick_matching_requests(scale_clock):
    clock, worker = scale_clock
    assert not pi_server._read_weight()[1]
    clock[0] = .1
    assert not pi_server._read_weight()[1]
    clock[0] = 1.1
    measurement, stable, in_range = pi_server._read_weight()
    assert stable and not in_range and measurement['weight_g'] == 125
    assert measurement['sample_noise_floor_g'] == 2
    clock[0] = 12
    assert not pi_server._read_weight()[1]  # stale window cannot authorize


def test_drift_persistent_noise_and_recovery(scale_clock):
    clock, worker = scale_clock
    for i, weight in enumerate([125,125.3,125.6,125.9,126.2,126.5,126.8]):
        clock[0] = i * .5
        worker.return_value = {'weight_g':weight, 'calibrated':True}
        measurement, stable, _ = pi_server._read_weight()
        assert not stable
    assert measurement['measurement_state'] == 'unstable'
    clock[0] = 4.1
    measurement, stable, _ = pi_server._read_weight()
    assert stable and measurement['measurement_state'] == 'calibrated'


def test_fault_resets_stability(scale_clock):
    clock, worker = scale_clock
    pi_server._read_weight()
    clock[0] = 1.1
    assert pi_server._read_weight()[1]
    worker.side_effect = RuntimeError('Disconnected')
    with pytest.raises(RuntimeError):
        pi_server._read_weight()
    worker.side_effect = None
    clock[0] = 1.2
    assert not pi_server._read_weight()[1]

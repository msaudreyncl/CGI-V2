"""Verify acquisition cadence with a deterministic clock, without physical GPIO."""
from pathlib import Path
import configparser
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'pi_node'))
import hx711_reader as scale


@pytest.fixture
def timed_sensor(monkeypatch):
    class Clock:
        now = 0.0
        def monotonic(self): return self.now
        def sleep(self, delay): self.now += delay
    clock = Clock()
    monkeypatch.setattr(scale.time, 'monotonic', clock.monotonic)
    monkeypatch.setattr(scale.time, 'sleep', clock.sleep)
    class Sensor:
        times = None
        def __init__(self): self.times = []
        def _read(self, **kwargs):
            self.times.append(clock.now)
            return 10000
    return Sensor(), clock


def test_calibration_reads_at_80_hz_across_batches(timed_sensor):
    sensor, clock = timed_sensor
    config = configparser.ConfigParser()
    config.read_dict({'load_cell': {'READINGS_TO_AVERAGE': '10'}})
    result = scale.collect_reference(sensor, config)
    assert result['samples'] == 30
    assert result['raw'] == 10000
    assert sensor.times == pytest.approx([i / 80 for i in range(30)])
    scale.raw_samples(sensor, 1)
    assert sensor.times[-1] == pytest.approx(30 / 80)


def test_deadline_stops_paced_reads(timed_sensor):
    sensor, clock = timed_sensor
    with pytest.raises(RuntimeError, match='valid samples'):
        scale.raw_samples(sensor, 10, timeout=.03)
    assert clock.now == pytest.approx(.03)
    assert sensor.times == pytest.approx([0, .0125, .025])


def test_blocking_adc_does_not_get_an_extra_delay(timed_sensor):
    sensor, clock = timed_sensor
    def blocking_read(**kwargs):
        sensor.times.append(clock.now)
        clock.sleep(1 / 80)
        return 10000
    sensor._read = blocking_read
    scale.raw_samples(sensor, 10)
    assert sensor.times == pytest.approx([i / 80 for i in range(10)])
    assert clock.now == pytest.approx(10 / 80)

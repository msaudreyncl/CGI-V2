"""Physical sample sequences exercise signed calibration, tare and noise handling."""
import configparser
from collections import deque
from pathlib import Path
import sys
import types
from unittest.mock import Mock

import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'pi_node'))
import hx711_reader as scale
import hardware_runtime


class Samples:
    def __init__(self, values):
        self.values = deque(values)
    def _read(self, **kwargs):
        return self.values.popleft() if self.values else False


def cfg():
    result = configparser.ConfigParser()
    result.read_dict({'load_cell': {'CALIBRATION_FACTOR':'1000', 'ZERO_OFFSET':'10000',
        'BASE_ZERO_OFFSET':'10000', 'CALIBRATION_VERIFIED':'true', 'READINGS_TO_AVERAGE':'10',
        'HX711_DT_PIN':'5', 'HX711_SCK_PIN':'6'}, 'camera': {'FOCUS_MODE':'manual'}})
    return result


@pytest.fixture
def config_file(monkeypatch, tmp_path):
    path = tmp_path / 'config.ini'
    monkeypatch.setattr(scale, 'CONFIG_PATH', str(path))
    scale.save_scale_config(cfg())
    return path


@pytest.mark.parametrize('value', [0, -1, -50000, 50000])
def test_valid_signed_raw_counts(value):
    assert scale.raw_mean(Samples([value] * 10)) == value


@pytest.mark.parametrize('factor', [1000, -1000])
def test_bare_platform_tray_tare_beans_and_removal(config_file, factor):
    config = scale._load_config()
    config.set('load_cell', 'CALIBRATION_FACTOR', str(factor))
    scale.save_scale_config(config)
    raw = lambda grams: 10000 + factor * grams
    assert scale.read_weight_g(Samples([raw(0)] * 10), config) == 0
    assert scale.read_weight_g(Samples([raw(100)] * 10), config) == 100
    hx = Samples([raw(100)] * 40)
    scale.tare(hx)
    tared = scale._load_config()  # Reopen, as after a server restart.
    assert tared.getfloat('load_cell', 'CALIBRATION_FACTOR') == factor
    assert tared.getfloat('load_cell', 'BASE_ZERO_OFFSET') == 10000
    assert tared.get('camera', 'FOCUS_MODE') == 'manual'
    assert scale.read_weight_g(Samples([raw(100)] * 10), tared) == 0
    assert scale.read_weight_g(Samples([raw(450)] * 10), tared) == 350
    assert scale.read_weight_g(Samples([raw(100)] * 10), tared) == 0
    # Removing the tared tray is a legitimate negative measurement.
    assert scale.read_weight_g(Samples([raw(0)] * 10), tared) == -100


def test_isolated_spike_is_filtered_but_movement_is_rejected():
    assert scale.read_weight_g(Samples([360000] * 9 + [7000000]), cfg()) == 350
    with pytest.raises(scale.UnstableScaleError):
        scale.read_weight_g(Samples([360000] * 7 + [7000000] * 3), cfg())
    with pytest.raises(scale.UnstableScaleError):
        scale.read_weight_g(Samples([360000 + i * 100 for i in range(10)]), cfg())


@pytest.mark.parametrize('invalid', [False, float('nan'), float('inf'), 8388607, -8388608])
def test_bad_samples_never_become_weights(invalid):
    with pytest.raises(RuntimeError, match='valid samples'):
        scale.read_weight_g(Samples([invalid] * 40), cfg())


def test_unstable_tare_keeps_previous_offset(config_file):
    before = config_file.read_bytes()
    with pytest.raises(scale.UnstableScaleError, match='Tare rejected'):
        scale.tare(Samples([10000] * 10 + [12000] * 10 + [14000] * 10))
    assert config_file.read_bytes() == before
    # A moving verification batch must also preserve the previous zero.
    with pytest.raises(scale.UnstableScaleError):
        scale.tare(Samples([10000] * 30 + [12000] * 10))
    assert config_file.read_bytes() == before


@pytest.mark.parametrize('sign', [1, -1])
def test_calibration_learns_polarity_from_known_mass(sign):
    assert scale.derive_calibration({'raw':10000, 'spread':20},
        {'raw':10000 + sign * 350000, 'spread':30}, 350, cfg()) == sign * 1000


@pytest.mark.parametrize('empty,loaded,mass', [
    ({'raw':10000,'spread':10}, {'raw':10114.5,'spread':10}, 23),
    ({'raw':10000,'spread':0}, {'raw':10000,'spread':0}, 350),
    ({'raw':10000,'spread':1000}, {'raw':360000,'spread':1000}, 350),
    ({'raw':10000,'spread':0}, {'raw':360000,'spread':0}, float('nan')),
])
def test_bad_calibration_is_rejected(empty, loaded, mass):
    with pytest.raises((ValueError, scale.UnstableScaleError)):
        scale.derive_calibration(empty, loaded, mass, cfg())


def test_legacy_and_invalid_calibration_is_not_trusted():
    config = cfg()
    config.remove_option('load_cell', 'CALIBRATION_VERIFIED')
    with pytest.raises(ValueError, match='verification'):
        scale.read_weight_g(Samples([10000] * 10), config)
    for key, value in [('CALIBRATION_FACTOR','0'), ('CALIBRATION_FACTOR','nan'), ('ZERO_OFFSET','inf')]:
        config = cfg()
        config.set('load_cell', key, value)
        with pytest.raises(ValueError):
            scale.read_weight_g(Samples([10000] * 10), config)


def test_persistent_worker_initializes_once_and_reloads_tare(monkeypatch, config_file):
    hx = Samples([110000] * 60)  # read, four tare batches, then read again.
    build = Mock(return_value=hx)
    monkeypatch.setattr(scale, '_build_hx711', build)
    gpio = types.ModuleType('RPi.GPIO')
    gpio.cleanup = Mock()
    rpi = types.ModuleType('RPi')
    rpi.GPIO = gpio
    monkeypatch.setitem(sys.modules, 'RPi', rpi)
    monkeypatch.setitem(sys.modules, 'RPi.GPIO', gpio)
    class Connection:
        operations = deque(['weight', 'tare', 'weight'])
        results = []
        def recv(self):
            if not self.operations:
                raise EOFError
            return self.operations.popleft()
        def send(self, result): self.results.append(result)
        def close(self): pass
    conn = Connection()
    hardware_runtime._scale_worker(conn)
    assert conn.results == [(True,100.0,None), (True,110000,None), (True,0.0,None)]
    build.assert_called_once()
    gpio.cleanup.assert_called_once()


@pytest.mark.parametrize('unload', [10000, 20000])
def test_wizard_verifies_load_and_return_to_zero(monkeypatch, config_file, unload):
    before = config_file.read_bytes()
    worker = Mock()
    worker.request.side_effect = [{'raw':10000,'spread':10}, {'raw':360000,'spread':10},
                                  {'raw':360000,'spread':10}] + [{'raw':unload,'spread':10}] * 6
    monkeypatch.setattr(scale.time, 'sleep', lambda _: None)
    monkeypatch.setattr(hardware_runtime, 'ScaleWorker', Mock(return_value=worker))
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'hardware')
    monkeypatch.setattr(sys, 'argv', ['hx711_reader.py','--calibrate'])
    answers = iter(['','350','',''])
    monkeypatch.setattr('builtins.input', lambda _: next(answers))
    if unload != 10000:
        with pytest.raises(SystemExit) as exc:
            scale.main()
        assert exc.value.code == 1
        assert config_file.read_bytes() == before
    else:
        scale.main()
        saved = scale._load_config()
        assert saved.getboolean('load_cell','CALIBRATION_VERIFIED')
        assert saved.getfloat('load_cell','CALIBRATION_FACTOR') == 1000
        assert saved.getfloat('load_cell','CALIBRATION_MASS_G') == 350
        assert saved.getfloat('load_cell','ZERO_OFFSET') == 10000
    worker.close.assert_called_once()


def test_worker_reuses_adc_after_unstable_batch(monkeypatch, config_file):
    context = Mock()
    conn, child = Mock(), Mock()
    context.Pipe.return_value = (conn, child)
    process = Mock()
    process.is_alive.return_value = True
    context.Process.return_value = process
    conn.poll.return_value = True
    conn.recv.side_effect = [(False, 'Scale moving', 'unstable'), (True, 350.0, None)]
    monkeypatch.setattr(hardware_runtime.multiprocessing, 'get_context', Mock(return_value=context))
    worker = hardware_runtime.ScaleWorker()
    try:
        with pytest.raises(scale.UnstableScaleError):
            worker.request('weight')
        assert worker.request('weight') == 350
        process.start.assert_called_once()
        process.terminate.assert_not_called()
    finally:
        worker.close()


def test_worker_deadline_reaps_and_next_request_reinitializes(monkeypatch, config_file):
    context = Mock()
    conn, child = Mock(), Mock()
    context.Pipe.return_value = (conn, child)
    process = Mock()
    process.is_alive.return_value = True
    context.Process.return_value = process
    conn.poll.side_effect = [False, True]
    conn.recv.return_value = (True, -12.25, None)
    monkeypatch.setattr(hardware_runtime.multiprocessing, 'get_context', Mock(return_value=context))
    worker = hardware_runtime.ScaleWorker()
    with pytest.raises(TimeoutError):
        worker.request('weight', timeout=0)
    assert worker.process is None and worker.conn is None
    process.terminate.assert_called_once()
    assert worker.request('weight') == -12.25
    assert process.start.call_count == 2
    worker.close()


def test_cli_script_continues_after_worker_reports_unstable(monkeypatch, config_file, capsys):
    # Running as a script used to define a second exception class under __main__,
    # so the worker's hx711_reader.UnstableScaleError escaped the inner handler.
    import runpy
    worker = Mock()
    worker.request.side_effect = [scale.UnstableScaleError('Sample noise'),
                                  {'raw':71000, 'spread':200}, KeyboardInterrupt]
    monkeypatch.setattr(hardware_runtime, 'ScaleWorker', Mock(return_value=worker))
    monkeypatch.setattr(scale.time, 'sleep', lambda _: None)
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'hardware')
    monkeypatch.setattr(sys, 'argv', ['hx711_reader.py', '--raw'])
    runpy.run_path(str(Path(scale.__file__)), run_name='__main__')
    output = capsys.readouterr().out
    assert 'UNSTABLE: Sample noise' in output and '71000' in output
    assert worker.request.call_count == 3
    worker.close.assert_called_once()


def test_idle_scale_close_allows_gpio_cleanup(monkeypatch):
    context = Mock()
    process, conn = Mock(), Mock()
    process.is_alive.side_effect = [True, False, False]
    worker = hardware_runtime.ScaleWorker()
    worker.process, worker.conn = process, conn
    worker.close()
    conn.send.assert_called_once_with('close')
    process.terminate.assert_not_called()
    conn.close.assert_called_once()
    assert worker.process is None and worker.conn is None


def test_gain_clock_overrun_leaves_clock_low_and_rejects(monkeypatch):
    gpio = Mock()
    monkeypatch.setattr(scale, 'GPIO', gpio, raising=False)
    ticks = iter([0.0, .00029192])
    monkeypatch.setattr(scale.time, 'perf_counter', lambda: next(ticks))
    hx = types.SimpleNamespace(_pd_sck=6)
    with pytest.raises(scale.UnstableScaleError, match='clock timing'):
        scale._safe_gain_pulses(hx, 1)
    assert hx._cgi_needs_settling is True
    assert gpio.output.call_args_list[-1].args == (6, False)


def test_settling_conversions_after_clock_error_never_enter_average():
    hx = Samples([700000] * 6 + [10000] * 10)
    hx._cgi_needs_settling = True
    assert scale.raw_mean(hx) == 10000
    assert hx._cgi_needs_settling is False


def test_invalid_conversion_abandons_partial_batch_and_resettles():
    hx = Samples([50000] * 3 + [False] + [700000] * 6 + [10000] * 10)
    assert scale.raw_mean(hx) == 10000
    assert hx._cgi_needs_settling is False


def test_terminal_reference_recovers_noise_and_acquisition_error(monkeypatch, capsys):
    worker = Mock()
    sample = {'raw':10000, 'spread':10}
    worker.request.side_effect = [scale.UnstableScaleError('spike'),
                                  RuntimeError('no conversion'), sample]
    monkeypatch.setattr(scale.time, 'sleep', lambda _: None)
    assert scale.terminal_reference(worker, 'Empty') == sample
    output = capsys.readouterr().out
    assert 'UNSTABLE' in output and 'ACQUISITION ERROR' in output


def test_terminal_reference_persistent_fault_is_bounded(monkeypatch):
    worker = Mock()
    worker.request.side_effect = RuntimeError('disconnected')
    monkeypatch.setattr(scale.time, 'sleep', lambda _: None)
    with pytest.raises(scale.UnstableScaleError, match='retry budget'):
        scale.terminal_reference(worker, 'Empty')
    assert worker.request.call_count == 6


def test_terminal_reference_waits_for_zero_without_relaxing_tolerance(monkeypatch):
    worker = Mock()
    worker.request.side_effect = [{'raw':12000, 'spread':10}, {'raw':10010, 'spread':20}]
    monkeypatch.setattr(scale.time, 'sleep', lambda _: None)
    result = scale.terminal_reference(worker, 'Zero', lambda sample:
        scale.verify_reference(sample, {'raw':10000}, 1000, cfg(), 'Zero'))
    assert result['raw'] == 10010


def test_cli_retries_acquisition_error_without_printing_fake_weight(monkeypatch, config_file, capsys):
    worker = Mock()
    worker.request.side_effect = [RuntimeError('disconnected'),
                                  {'raw':71000, 'spread':200}, KeyboardInterrupt]
    monkeypatch.setattr(hardware_runtime, 'ScaleWorker', Mock(return_value=worker))
    monkeypatch.setattr(scale.time, 'sleep', lambda _: None)
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'hardware')
    monkeypatch.setattr(sys, 'argv', ['hx711_reader.py', '--raw'])
    scale.main()
    output = capsys.readouterr().out
    assert 'ACQUISITION ERROR: disconnected' in output and '71000' in output
    assert '0.00 g' not in output
    worker.close.assert_called_once()


def test_reference_reports_outlier_counts():
    sample = scale.collect_reference(Samples(([10000] * 9 + [7000000]) * 3), cfg())
    assert sample['raw'] == 10000
    assert sample['samples'] == 30 and sample['rejected'] == 3


def test_new_load_replaces_previous_batch_without_smoothing_old_weight():
    hx = Samples([10000] * 10 + [360000] * 10 + [10000] * 10)
    assert [scale.read_weight_g(hx, cfg()) for _ in range(3)] == [0, 350, 0]


def test_terminal_load_transition_requires_fresh_agreement(monkeypatch, config_file, capsys):
    worker = Mock()
    worker.request.side_effect = [0.0, 0.0, 350.0, 350.0,
                                  scale.UnstableScaleError('noise'), -12.0, -12.0, KeyboardInterrupt]
    monkeypatch.setattr(hardware_runtime, 'ScaleWorker', Mock(return_value=worker))
    monkeypatch.setattr(scale.time, 'sleep', lambda _: None)
    monkeypatch.setenv('CGI_HARDWARE_MODE', 'hardware')
    monkeypatch.setattr(sys, 'argv', ['hx711_reader.py'])
    scale.main()
    lines = capsys.readouterr().out.splitlines()
    assert [line for line in lines if line.endswith(' g')] == ['0.00 g', '350.00 g', '-12.00 g']
    assert sum('waiting for consistent' in line for line in lines) == 3


@pytest.mark.parametrize('raw', [0, -1, -50000, 7000000])
def test_acquisition_mode_preserves_single_conversion_without_verification(raw):
    config = cfg()
    config.set('load_cell', 'WEIGHT_TEST_MODE', 'true')
    config.set('load_cell', 'CALIBRATION_VERIFIED', 'false')
    adc = Samples([raw, 12345])
    assert scale.read_weight_g(adc, config) == (raw - 10000) / 1000
    assert list(adc.values) == [12345]  # No filtering or averaging.


def test_acquisition_mode_disconnection_never_becomes_zero():
    config = cfg()
    config.set('load_cell', 'WEIGHT_TEST_MODE', 'true')
    with pytest.raises(RuntimeError):
        scale.read_weight_g(Samples([False] * 40), config)

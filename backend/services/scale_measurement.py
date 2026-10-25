"""Shared validation for Pi measurements; range bypass never grants validity."""
import math
from datetime import datetime, timezone

MAX_READING_AGE_S = 10


def measurement_status(data, bypass_enabled=False):
    result = dict(data)
    weight = data.get('weight_g')
    try:
        measured = datetime.fromisoformat(data['measured_at'].replace('Z', '+00:00'))
        age = (datetime.now(timezone.utc) - measured).total_seconds()
        fresh = 0 <= age <= MAX_READING_AGE_S
    except (KeyError, ValueError, TypeError, AttributeError):
        fresh = False
    valid = (data.get('calibrated') is True and data.get('simulated') is False
             and data.get('scale') == 'ready' and data.get('stable') is True
             and isinstance(weight, (int, float)) and not isinstance(weight, bool)
             and math.isfinite(weight) and fresh)
    floor = data.get('sample_noise_floor_g', 1.0)
    if not isinstance(floor, (int, float)) or isinstance(floor, bool) or not math.isfinite(floor) or floor <= 0:
        floor = 1.0
    sample_present = valid and weight > floor
    bypass = (bypass_enabled and data.get('weight_test_mode') is True
              and data.get('simulated') is False)
    in_range = isinstance(weight, (int, float)) and not isinstance(weight, bool) and math.isfinite(weight) and 340 <= weight <= 360
    result.update(valid_weight=valid, bypass_weight_range=bypass,
                  weight_test_mode=bypass, in_range=in_range,
                  sample_present=sample_present,
                  weight_gate_passed=sample_present and (bypass or in_range))
    if not valid:
        result['weight_g'] = None
        if data.get('scale') != 'ready':
            message = 'Scale unavailable'
        elif data.get('measurement_state') == 'unstable':
            message = 'Scale unstable'
        elif data.get('calibrated') is not True and data.get('measurement_state') != 'unstable':
            message = 'Calibration required'
        elif not fresh:
            message = 'Reading expired — reconnecting…'
        else:
            message = 'Stabilizing…'
        result['status_message'] = message
    elif not sample_present:
        result['status_message'] = 'Empty tray — add beans'
    elif not bypass and not in_range:
        result['status_message'] = 'Add beans' if weight < 340 else 'Remove beans'
    else:
        result['status_message'] = 'Stable'
    return result


_latest_sensor_reading = None


def sensor_testing_status(data):
    """Keep acquisition diagnostics separate from transaction grams and normal gating."""
    global _latest_sensor_reading
    result = dict(data)
    if data.get('scale') == 'ready' and data.get('simulated') is False:
        grams = data.get('weight_g')
        raw = data.get('raw_counts', data.get('raw_adc'))
        calibrated = data.get('calibrated') is True
        value = grams if calibrated else raw
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            candidate = {'value':value, 'unit':'g' if calibrated else 'ADC counts',
                         'raw_counts':raw, 'calibrated':calibrated,
                         'measured_at':data.get('measured_at')}
            if (_latest_sensor_reading is None or
                str(candidate['measured_at'] or '') >= str(_latest_sensor_reading['measured_at'] or '')):
                _latest_sensor_reading = candidate
            result['sensor_reading'] = candidate
    result.update(sensor_test_mode=True, weight_gate_passed=True,
                  latest_sensor_reading=_latest_sensor_reading)
    return result

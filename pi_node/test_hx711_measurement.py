"""GPIO-free measurement/merge regressions.

Run: python3 -m unittest discover -s pi_node -p test_hx711_measurement.py -v
"""
import configparser
import unittest
from unittest.mock import Mock, patch
import hx711_reader as reader
import pi_server


def config(factor='1', offset='0', verified=False, sensor=False):
    cfg = configparser.ConfigParser()
    cfg.read_dict({'load_cell': {
        'CALIBRATION_FACTOR': factor, 'ZERO_OFFSET': offset,
        'CALIBRATION_VERIFIED': str(verified),
        'WEIGHT_SENSOR_TEST_MODE': str(sensor),
        'READINGS_TO_AVERAGE': '10'}})
    return cfg


class MeasurementTests(unittest.TestCase):
    def measurement(self, cfg, raw=1000000):
        hx = Mock()
        hx._cgi_next_read_at = 0.0
        hx._cgi_needs_settling = False
        hx._read.return_value = raw
        with patch.object(reader, 'SAMPLE_INTERVAL_S', 0):
            return reader.read_measurement(hx, cfg)

    def test_million_counts_are_not_grams(self):
        result = self.measurement(config())
        self.assertEqual(result['raw_adc'], 1000000)
        self.assertEqual(result['raw_samples_adc'], [1000000])
        self.assertIsNone(result['weight_g'])
        self.assertFalse(result['calibrated'])
        self.assertEqual(result['measurement_unit'], 'ADC counts')

    def test_verified_negative_calibration(self):
        result = self.measurement(config('-100', '10000', verified=True), -25000)
        self.assertEqual(result['weight_g'], 350)
        self.assertEqual(result['raw_adc'], -25000)
        self.assertEqual(result['raw_samples_adc'], [-25000] * 10)
        self.assertTrue(result['calibrated'])
        self.assertEqual(result['measurement_unit'], 'g')

    def test_unverified_factor_is_not_used(self):
        self.assertIsNone(self.measurement(config('-100', '10000'), -25000)['weight_g'])

    def test_invalid_or_missing_calibration(self):
        for factor in ('0', 'nan', 'inf', 'bad'):
            with self.subTest(factor=factor):
                self.assertIsNone(self.measurement(config(factor, verified=True))['weight_g'])
        cfg = config('100', verified=True)
        cfg.remove_option('load_cell', 'ZERO_OFFSET')
        self.assertIsNone(self.measurement(cfg)['weight_g'])

    def test_saturation_disconnect_and_invalid_samples(self):
        for raw in (False, None, 8388607, -8388608, 9000000, float('nan'), float('inf')):
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                self.measurement(config(sensor=True), raw)

    def test_sensor_mode_preserves_signed_raw_readings(self):
        for raw in (0, -1, -1000000, 1000000):
            with self.subTest(raw=raw):
                result = self.measurement(config(sensor=True), raw)
                self.assertEqual(result['raw_adc'], raw)
                self.assertIsNone(result['weight_g'])

    def test_sensor_mode_keeps_large_and_negative_grams(self):
        for raw in (0, -1000000, 1000000):
            with self.subTest(raw=raw):
                result = self.measurement(config('.01', verified=True, sensor=True), raw)
                self.assertEqual(result['weight_g'], raw / .01)

    def test_raw_never_becomes_valid_weight(self):
        measurement = self.measurement(config())
        with patch.object(pi_server, '_load_config', return_value=config()), \
             patch.object(pi_server, 'simulated', return_value=False), \
             patch.object(pi_server._scale_worker, 'request', return_value=measurement):
            pi_server._last_weight = 350
            result, stable, in_range = pi_server._read_weight()
        self.assertIsNone(result['weight_g'])
        self.assertFalse(stable)
        self.assertFalse(in_range)
        self.assertIsNone(pi_server._last_weight)

    def test_calibrated_range_and_duration_stability(self):
        cfg = config('-100', '10000', verified=True)
        with patch.object(pi_server, '_load_config', return_value=cfg), \
             patch.object(pi_server, 'simulated', return_value=False):
            for weight in (339, 340, 350, 360, 361):
                with self.subTest(weight=weight), \
                     patch.object(pi_server._scale_worker, 'request', side_effect=lambda *a, **k: {
                         'weight_g': weight, 'raw_adc': 10000-weight*100, 'calibrated': True}), \
                     patch.object(pi_server.time, 'monotonic', side_effect=[100, 100.5, 101.1]):
                    pi_server._last_weight = None
                    first = pi_server._read_weight()
                    second = pi_server._read_weight()
                    third = pi_server._read_weight()
                    self.assertFalse(first[1])
                    self.assertFalse(second[1])
                    self.assertTrue(third[1])
                    self.assertEqual(third[2], 340 <= weight <= 360)

    def test_sensor_mode_does_not_apply_range_or_stability(self):
        cfg = config(sensor=True)
        for weight in (None, 0, -1000000, 1000000):
            measurement = {'weight_g': weight, 'raw_adc': -123, 'calibrated': weight is not None}
            with self.subTest(weight=weight), \
                 patch.object(pi_server, '_load_config', return_value=cfg), \
                 patch.object(pi_server, 'simulated', return_value=False), \
                 patch.object(pi_server._scale_worker, 'request', return_value=measurement):
                result, stable, in_range = pi_server._read_weight()
                self.assertEqual(result, measurement)
                self.assertFalse(stable)
                self.assertFalse(in_range)

    def test_hardware_failure_is_not_replaced_with_fake_reading(self):
        with patch.object(pi_server, '_load_config', return_value=config(sensor=True)), \
             patch.object(pi_server, 'simulated', return_value=False), \
             patch.object(pi_server._scale_worker, 'request', side_effect=RuntimeError('Disconnected')):
            with self.assertRaisesRegex(RuntimeError, 'Disconnected'):
                pi_server._read_weight()
            self.assertIsNone(pi_server._last_weight)


if __name__ == '__main__':
    unittest.main()

"""GPIO-free regression checks: python -m unittest discover -s pi_node -p test_hx711_measurement.py -v"""
import configparser
import unittest
from unittest.mock import Mock, patch
import hx711_reader as reader
import pi_server


def config(factor='1', offset='0'):
    cfg = configparser.ConfigParser()
    cfg.read_dict({'load_cell': {'CALIBRATION_FACTOR': factor, 'ZERO_OFFSET': offset,
                                'READINGS_TO_AVERAGE': '10'}})
    return cfg


class MeasurementTests(unittest.TestCase):
    def measurement(self, cfg, raw=1000000):
        hx = Mock()
        hx.get_raw_data.return_value = [raw] * 14
        return reader.read_measurement(hx, cfg)

    def test_million_counts_are_not_grams(self):
        result = self.measurement(config())
        self.assertEqual(result['raw_adc'], 1000000)
        self.assertEqual(result['raw_samples_adc'], [1000000] * 14)
        self.assertIsNone(result['weight_g'])
        self.assertFalse(result['calibrated'])
        self.assertEqual(result['measurement_unit'], 'ADC counts')

    def test_existing_negative_calibration(self):
        result = self.measurement(config('-100', '10000'), -25000)
        self.assertEqual(result['weight_g'], 350)
        self.assertEqual(result['raw_adc'], -25000)
        self.assertTrue(result['calibrated'])

    def test_invalid_or_missing_calibration(self):
        for factor in ('0', 'nan', 'inf', 'bad', '-1'):
            with self.subTest(factor=factor):
                self.assertIsNone(self.measurement(config(factor))['weight_g'])
        cfg = config('100')
        cfg.remove_option('load_cell', 'ZERO_OFFSET')
        self.assertIsNone(self.measurement(cfg)['weight_g'])
        cfg = config('100')
        cfg.set('load_cell', 'CALIBRATED', 'false')
        self.assertIsNone(self.measurement(cfg)['weight_g'])

    def test_saturation_disconnect_and_invalid_samples(self):
        for samples in (False, None, [False]*14, [None]*14, [8388607]*14,
                        [-8388608]*14, [9000000]*14, [float('nan')]*14):
            with self.subTest(samples=samples):
                hx = Mock()
                hx.get_raw_data.return_value = samples
                with patch.object(reader.time, 'sleep'), self.assertRaises(RuntimeError):
                    reader.read_measurement(hx, config())

    def test_raw_never_becomes_valid_weight(self):
        result = self.measurement(config())
        with patch.object(pi_server, '_load_config', return_value=config()), \
             patch.object(pi_server, 'simulated', return_value=False), \
             patch.object(pi_server, 'run_hardware', return_value=result):
            pi_server._last_weight = 350
            result = pi_server._read_weight()
        self.assertIsNone(result['weight_g'])
        self.assertFalse(result['stable'])
        self.assertFalse(result['in_range'])
        self.assertIsNone(pi_server._last_weight)

    def test_calibrated_range_and_stability(self):
        cfg = config('-100', '10000')
        with patch.object(pi_server, '_load_config', return_value=cfg), \
             patch.object(pi_server, 'simulated', return_value=False):
            for weight in (339, 340, 350, 360, 361):
                with patch.object(pi_server, 'run_hardware', return_value={
                        'weight_g': weight, 'raw_adc': 10000-weight*100, 'calibrated': True}):
                    pi_server._last_weight = None
                    first = pi_server._read_weight()
                    second = pi_server._read_weight()
                self.assertFalse(first['stable'])
                self.assertTrue(second['stable'])
                self.assertEqual(second['in_range'], 340 <= weight <= 360)


if __name__ == '__main__':
    unittest.main()
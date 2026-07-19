import math
import unittest
from unittest.mock import mock_open, patch

from scanner_auto_pa import (
    ScannerAutoPA,
    pressure_proxy,
    volumetric_flow_to_e_distance,
)


class ScannerAutoPATest(unittest.TestCase):
    def setUp(self):
        self.auto_pa = ScannerAutoPA.__new__(ScannerAutoPA)
        self.auto_pa.min_samples = 3

    def test_volumetric_flow_converts_to_filament_distance(self):
        result = volumetric_flow_to_e_distance(10.0, 2.0, 2.0)
        self.assertAlmostEqual(result, 20.0 / math.pi)

    def test_pressure_proxy_increases_when_frequency_falls(self):
        self.assertEqual(pressure_proxy(1000.0, 998.0), 2.0)
        self.assertEqual(pressure_proxy(1000.0, 1001.0), -1.0)

    def test_candidate_analysis_returns_metrics_for_valid_samples(self):
        baseline = [{"freq": 1000.0}, {"freq": 1000.2}, {"freq": 999.8}]
        samples = [{"freq": 998.0}, {"freq": 997.0}, {"freq": 998.5}]

        result = self.auto_pa._analyse_candidate(0.04, baseline, samples)

        self.assertTrue(result["valid"])
        self.assertEqual(result["k"], 0.04)
        self.assertEqual(result["sample_count"], 3)
        self.assertGreater(result["overshoot"], 0.0)
        self.assertGreater(result["score"], 0.0)

    def test_candidate_analysis_rejects_insufficient_samples(self):
        result = self.auto_pa._analyse_candidate(
            0.04, [{"freq": 1000.0}], [{"freq": 998.0}]
        )

        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "insufficient Scanner samples")

    def test_debug_export_writes_baseline_and_test_rows(self):
        mocked_open = mock_open()
        baseline = [{"time": 1.0, "data": 100, "freq": 1000.0, "temp": 25.0, "pos": [1, 2, 3]}]
        samples = [{"time": 2.0, "data": 98, "freq": 998.0, "temp": 25.0, "pos": [2, 2, 3]}]

        with patch("builtins.open", mocked_open):
            self.auto_pa._export_debug("pa-debug.csv", baseline, samples)

        self.assertTrue(mocked_open.called)


if __name__ == "__main__":
    unittest.main()

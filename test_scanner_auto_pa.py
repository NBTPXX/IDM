import math
import unittest
from unittest.mock import Mock, mock_open, patch

from scanner_auto_pa import (
    ScannerAutoPA,
    build_bed_line_plan,
    pressure_proxy,
    volumetric_flow_to_e_distance,
    volumetric_flow_to_line_distance,
)


class ScannerAutoPATest(unittest.TestCase):
    def setUp(self):
        self.auto_pa = ScannerAutoPA.__new__(ScannerAutoPA)
        self.auto_pa.min_samples = 3

    def test_volumetric_flow_converts_to_filament_distance(self):
        result = volumetric_flow_to_e_distance(10.0, 2.0, 2.0)
        self.assertAlmostEqual(result, 20.0 / math.pi)

    def test_volumetric_flow_converts_to_printed_line_distance(self):
        result = volumetric_flow_to_line_distance(9.0, 0.5, 0.45, 0.2)
        self.assertAlmostEqual(result, 50.0)

    def test_bed_line_plan_separates_candidates_and_alternates_direction(self):
        plan = build_bed_line_plan(10.0, 20.0, 50.0, 1.0, 2, 2)

        self.assertEqual(len(plan), 2)
        self.assertEqual(plan[0][0], {
            "start_x": 10.0, "end_x": 60.0, "y": 20.0, "direction": 1.0,
        })
        self.assertEqual(plan[0][1], {
            "start_x": 60.0, "end_x": 10.0, "y": 21.0, "direction": -1.0,
        })
        self.assertEqual(plan[1][0]["y"], 22.0)

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

    def test_settings_include_configured_baseline_time(self):
        gcmd = Mock()
        gcmd.get_float.side_effect = lambda name, default, **kwargs: default
        gcmd.get_int.side_effect = lambda name, default, **kwargs: default
        gcmd.get.side_effect = lambda name, default: default
        self.auto_pa.baseline_time = 1.25

        settings = self.auto_pa._settings(gcmd)

        self.assertEqual(settings["baseline_time"], 1.25)
        self.assertEqual(settings["cycles"], 1)
        self.assertEqual(settings["layer_height"], 0.2)
        self.assertEqual(settings["line_width"], 0.45)
        self.assertEqual(settings["z_speed"], 10.0)

    def test_bed_line_planning_accounts_for_scanner_offset(self):
        self.auto_pa.printer = Mock()
        self.auto_pa.printer.get_reactor.return_value.monotonic.return_value = 1.0
        self.auto_pa.scanner = Mock()
        self.auto_pa.scanner.offset = {"x": 10.0, "y": -5.0}
        toolhead = Mock()
        toolhead.get_kinematics.return_value.get_status.return_value = {
            "axis_minimum": [0.0, 0.0, 0.0],
            "axis_maximum": [220.0, 220.0, 250.0],
        }
        gcmd = Mock()
        gcmd.get_float.side_effect = lambda name, default, **kwargs: default
        settings = {
            "cycles": 1,
            "low_flow": 1.0,
            "high_flow": 2.0,
            "low_time": 1.0,
            "high_time": 1.0,
            "layer_height": 0.2,
            "line_width": 0.5,
            "line_spacing": 1.0,
            "z_hop": 2.0,
        }

        plan = self.auto_pa._plan_bed_lines(toolhead, gcmd, settings, 2)

        self.assertEqual(plan[0][0]["start_x"], 5.0)
        self.assertEqual(plan[0][0]["y"], 10.0)
        self.assertEqual(plan[1][0]["y"], 11.0)
        self.assertEqual(settings["travel_z"], 2.2)

    def test_bed_line_planning_rejects_insufficient_space(self):
        self.auto_pa.printer = Mock()
        self.auto_pa.printer.get_reactor.return_value.monotonic.return_value = 1.0
        self.auto_pa.scanner = Mock()
        self.auto_pa.scanner.offset = {"x": 0.0, "y": 0.0}
        toolhead = Mock()
        toolhead.get_kinematics.return_value.get_status.return_value = {
            "axis_minimum": [0.0, 0.0, 0.0],
            "axis_maximum": [30.0, 30.0, 250.0],
        }
        gcmd = Mock()
        gcmd.get_float.side_effect = lambda name, default, **kwargs: default
        gcmd.error.side_effect = lambda message: ValueError(message)
        settings = {
            "cycles": 1,
            "low_flow": 1.0,
            "high_flow": 2.0,
            "low_time": 1.0,
            "high_time": 1.0,
            "layer_height": 0.2,
            "line_width": 0.5,
            "line_spacing": 1.0,
            "z_hop": 2.0,
        }

        with self.assertRaisesRegex(ValueError, "require X"):
            self.auto_pa._plan_bed_lines(toolhead, gcmd, settings, 1)

    def test_printed_bed_line_uses_absolute_segment_targets(self):
        self.auto_pa.gcode = Mock()
        self.auto_pa.filament_diameter = 2.0
        settings = {
            "low_flow": 1.0,
            "high_flow": 2.0,
            "low_time": 1.0,
            "high_time": 1.0,
            "segment_distances": [10.0, 20.0, 10.0],
        }
        line = {"start_x": 50.0, "direction": -1.0}

        self.auto_pa._print_bed_line(line, settings)

        commands = [
            call.args[0]
            for call in self.auto_pa.gcode.run_script_from_command.call_args_list
        ]
        self.assertEqual(commands, [
            "G1 X40.00000 E0.318310 F600.000",
            "G1 X20.00000 E0.636620 F1200.000",
            "G1 X10.00000 E0.318310 F600.000",
        ])

    def test_debug_export_writes_baseline_and_test_rows(self):
        mocked_open = mock_open()
        baseline = [{"time": 1.0, "data": 100, "freq": 1000.0, "temp": 25.0, "pos": [1, 2, 3]}]
        samples = [{"time": 2.0, "data": 98, "freq": 998.0, "temp": 25.0, "pos": [2, 2, 3]}]

        with patch("builtins.open", mocked_open):
            self.auto_pa._export_debug("pa-debug.csv", baseline, samples)

        self.assertTrue(mocked_open.called)


if __name__ == "__main__":
    unittest.main()

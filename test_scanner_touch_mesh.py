import math
import unittest

from scanner_touch_mesh import (
    COMPENSATION_SECTION,
    CompensationProfile,
    align_matrices_at_center,
    arc_retract_segments,
    apply_compensation,
    difference_matrix,
    interpolate_matrix,
    matrix_range,
    needs_touch_retry,
    fill_round_mesh_edges,
    mesh_probe_indices,
    nearest_orbit_point_in_direction,
    round_lattice_orbits,
    round_lattice_layers,
    rounded_layer_mesh_trajectory,
    rounded_matrix_trajectory,
    round_mesh_trajectory,
    round_mesh_row_indices,
)


class FakeSection:
    def __init__(self, values):
        self.values = values

    def get(self, name):
        return self.values[name]

    def getint(self, name, default=None):
        value = self.values.get(name, default)
        return int(value) if value is not None else None


class FakeConfig:
    def __init__(self, values=None):
        self.values = values

    def has_section(self, name):
        return name == COMPENSATION_SECTION and self.values is not None

    def getsection(self, name):
        return FakeSection(self.values)


class FakeConfigFile:
    def __init__(self):
        self.values = {}

    def set(self, section, name, value):
        self.values[name] = value


class CompensationProfileTest(unittest.TestCase):
    def test_profile_round_trips_through_config_values(self):
        profile = CompensationProfile(0, 100, 0, 100, 2, 2, [[0.1, 0.2], [0.3, 0.4]])
        configfile = FakeConfigFile()

        profile.save(configfile)
        loaded = CompensationProfile.load(FakeConfig(configfile.values))

        self.assertEqual(loaded.matrix, profile.matrix)
        self.assertEqual((loaded.min_x, loaded.max_y), (0.0, 100.0))

    def test_disabled_or_missing_profile_is_not_loaded(self):
        self.assertIsNone(CompensationProfile.load(FakeConfig()))
        self.assertIsNone(CompensationProfile.load(FakeConfig({"enabled": "0"})))

    def test_invalid_matrix_dimensions_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "column count"):
            CompensationProfile(0, 10, 0, 10, 2, 2, [[0, 1], [2]])

    def test_invalid_saved_row_is_rejected(self):
        values = {
            "enabled": "1",
            "version": "1",
            "mesh_min": "0,0",
            "mesh_max": "10,10",
            "probe_count": "2,2",
            "row_0": "0,1",
            "row_1": "bad,2",
        }

        with self.assertRaisesRegex(ValueError, "row_1"):
            CompensationProfile.load(FakeConfig(values))

    def test_clear_disables_saved_profile(self):
        configfile = FakeConfigFile()

        CompensationProfile.clear(configfile)

        self.assertEqual(configfile.values["enabled"], "0")

    def test_difference_matrix_matches_touch_mesh_when_added_to_scanner_mesh(self):
        scanner = [[1.0, 1.5], [2.0, 2.5]]
        touch = [[1.1, 1.4], [2.3, 2.4]]

        compensation = difference_matrix(touch, scanner)

        self.assertEqual(
            [[scanner[y][x] + compensation[y][x] for x in range(2)] for y in range(2)],
            touch,
        )
        self.assertEqual(matrix_range(compensation), (-0.10000000000000009, 0.2999999999999998))

    def test_difference_matrix_rejects_dimension_mismatch(self):
        with self.assertRaisesRegex(ValueError, "dimensions"):
            difference_matrix([[1, 2]], [[1], [2]])

    def test_interpolation_preserves_linear_scanner_surface(self):
        matrix = [[0.0, 1.0], [1.0, 2.0]]

        value = interpolate_matrix(matrix, 0, 10, 0, 10, 2, 2, 2.5, 7.5)

        self.assertAlmostEqual(value, 1.0)

    def test_interpolation_returns_none_outside_mesh(self):
        matrix = [[0.0, 1.0], [1.0, 2.0]]

        self.assertIsNone(interpolate_matrix(matrix, 0, 10, 0, 10, 2, 2, -0.1, 5))

    def test_retry_only_when_difference_exceeds_threshold(self):
        self.assertTrue(needs_touch_retry(1.06, 1.0, 0.05))
        self.assertFalse(needs_touch_retry(1.05, 1.0, 0.05))

    def test_compensation_applies_linear_gradient_at_scanner_coordinates(self):
        profile = CompensationProfile(0, 10, 0, 10, 2, 2, [[0, 1], [1, 2]])
        compensated, uncovered = apply_compensation(
            profile, [[1, 1, 1], [1, 1, 1], [1, 1, 1]], 0, 10, 0, 10
        )

        self.assertEqual(uncovered, [])
        self.assertEqual(compensated, [[1, 1.5, 2], [1.5, 2, 2.5], [2, 2.5, 3]])

    def test_compensation_keeps_raw_values_outside_profile_coverage(self):
        profile = CompensationProfile(0, 10, 0, 10, 2, 2, [[0.5, 0.5], [0.5, 0.5]])
        compensated, uncovered = apply_compensation(
            profile, [[1, 1, 1], [1, 1, 1]], 0, 20, 0, 10
        )

        self.assertEqual(compensated, [[1.5, 1.5, 1], [1.5, 1.5, 1]])
        self.assertEqual(uncovered, [(20.0, 0.0), (20.0, 10.0)])

    def test_center_alignment_removes_global_height_offset(self):
        scanner = [[1, 2], [3, 4]]
        touch = [[3, 4], [5, 6]]

        centered_touch, centered_scanner = align_matrices_at_center(
            touch, scanner, 0, 10, 0, 10
        )

        self.assertEqual(difference_matrix(centered_touch, centered_scanner), [[0, 0], [0, 0]])

    def test_arc_retract_limits_radius_and_ends_with_travel_speed(self):
        segments = arc_retract_segments([0, 0], 0, [20, 0], 5, 5, 50)
        arc_end, arc_speed = segments[-2]

        self.assertAlmostEqual(arc_end[0], 5.0)
        self.assertEqual(arc_end[1:], [0.0, 5.0])
        self.assertEqual(segments[-1], ([20, 0, 5], 50))
        previous = segments[-3][0]
        xy_delta = arc_end[0] - previous[0]
        z_delta = arc_end[2] - previous[2]
        segment_distance = (xy_delta**2 + z_delta**2) ** 0.5
        self.assertAlmostEqual(arc_speed * z_delta / segment_distance, 5.0)
        self.assertAlmostEqual(arc_speed * xy_delta / segment_distance, 50.0)

    def test_arc_retract_uses_horizontal_distance_as_short_radius_limit(self):
        segments = arc_retract_segments([0, 0], 0, [3, 0], 5, 5, 50)

        self.assertAlmostEqual(segments[-2][0][0], 3.0)
        self.assertEqual(segments[-2][0][1:], [0.0, 3.0])
        self.assertEqual(segments[-1], ([3, 0, 5], 5))

    def test_round_mesh_rows_follow_klipper_circle_geometry(self):
        rows = [round_mesh_row_indices(5, index) for index in range(5)]

        self.assertEqual(rows, [[2], [1, 2, 3], [0, 1, 2, 3, 4], [1, 2, 3], [2]])

    def test_round_mesh_pads_corners_with_row_edge_measurements(self):
        matrix = [
            [None, None, 1.0, None, None],
            [None, 2.0, 3.0, 4.0, None],
            [5.0, 6.0, 7.0, 8.0, 9.0],
            [None, 10.0, 11.0, 12.0, None],
            [None, None, 13.0, None, None],
        ]
        rows = [round_mesh_row_indices(5, index) for index in range(5)]

        filled = fill_round_mesh_edges(matrix, rows)

        self.assertEqual(
            filled,
            [
                [1.0, 1.0, 1.0, 1.0, 1.0],
                [2.0, 2.0, 3.0, 4.0, 4.0],
                [5.0, 6.0, 7.0, 8.0, 9.0],
                [10.0, 10.0, 11.0, 12.0, 12.0],
                [13.0, 13.0, 13.0, 13.0, 13.0],
            ],
        )

    def test_round_mesh_probe_order_matches_klipper_serpentine_path(self):
        self.assertEqual(
            mesh_probe_indices(5, 5, circular=True),
            [
                (2, 0),
                (3, 1),
                (2, 1),
                (1, 1),
                (0, 2),
                (1, 2),
                (2, 2),
                (3, 2),
                (4, 2),
                (3, 3),
                (2, 3),
                (1, 3),
                (2, 4),
            ],
        )

    def test_round_lattice_orbits_cover_each_non_center_target_once(self):
        orbits = round_lattice_orbits(5)

        self.assertEqual(len(orbits), 3)
        self.assertEqual({point for orbit in orbits for point in orbit}, {
            (2, 0), (0, 2), (-2, 0), (0, -2),
            (1, 1), (-1, 1), (-1, -1), (1, -1),
            (1, 0), (0, 1), (-1, 0), (0, -1),
        })

    def test_round_lattice_layers_remove_the_outer_x_y_boundary(self):
        layers, matrix_points = round_lattice_layers(5)

        self.assertEqual(layers, [{(2, 0), (0, 2), (-2, 0), (0, -2)}])
        self.assertEqual(matrix_points, {
            (x, y) for y in range(-1, 2) for x in range(-1, 2)
        })

    def test_round_lattice_layers_stop_at_the_first_complete_inner_matrix(self):
        layers, matrix_points = round_lattice_layers(15)

        self.assertGreater(len(layers), 1)
        self.assertEqual(matrix_points, {
            (x, y) for y in range(-4, 5) for x in range(-4, 5)
        })
        outer_extents = [max(max(abs(x), abs(y)) for x, y in layer) for layer in layers]
        self.assertEqual(outer_extents, sorted(outer_extents, reverse=True))
        self.assertTrue(all(
            all(max(abs(x), abs(y)) == extent for x, y in layer)
            for layer, extent in zip(layers, outer_extents)
        ))

    def test_round_mesh_trajectory_visits_targets_then_stops_at_center(self):
        trajectory = round_mesh_trajectory((0, 0), 2, 5)
        targets = {
            (2, 0), (0, 2), (-2, 0), (0, -2),
            (1, 1), (-1, 1), (-1, -1), (1, -1),
            (1, 0), (0, 1), (-1, 0), (0, -1),
        }
        rounded = {(round(x, 6), round(y, 6)) for x, y in trajectory}

        self.assertTrue(targets.issubset(rounded))
        self.assertEqual(trajectory[-1], (0, 0))

    def test_orbit_start_uses_nearest_angular_point_in_travel_direction(self):
        points = [(1, 0), (0, 1), (-1, 0), (0, -1)]

        self.assertEqual(nearest_orbit_point_in_direction(points, -2.0, 1), 3)
        self.assertEqual(nearest_orbit_point_in_direction(points, 2.0, -1), 1)

    def test_round_mesh_trajectory_covers_shared_radius_orbits(self):
        trajectory = round_mesh_trajectory((0, 0), 3, 7)
        targets = {
            (xi - 3, yi - 3)
            for xi, yi in mesh_probe_indices(7, 7, circular=True)
        }
        rounded = {(round(x, 6), round(y, 6)) for x, y in trajectory}

        self.assertTrue(targets.issubset(rounded))

    def test_rounded_layer_trajectory_visits_every_round_mesh_target(self):
        trajectory = rounded_layer_mesh_trajectory((0, 0), 3, 7)
        targets = {
            (xi - 3, yi - 3)
            for xi, yi in mesh_probe_indices(7, 7, circular=True)
        }

        def lies_on_path(point):
            for start, end in zip(trajectory, trajectory[1:]):
                dx, dy = end[0] - start[0], end[1] - start[1]
                length_squared = dx * dx + dy * dy
                if length_squared == 0:
                    continue
                ratio = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared
                if 0 <= ratio <= 1:
                    nearest_x = start[0] + ratio * dx
                    nearest_y = start[1] + ratio * dy
                    if math.hypot(point[0] - nearest_x, point[1] - nearest_y) < 1.0e-6:
                        return True
            return False

        self.assertTrue(all(lies_on_path(point) for point in targets))
        self.assertTrue(all(math.hypot(x, y) <= 3 + 1.0e-9 for x, y in trajectory))

    def test_rounded_layer_trajectory_stays_within_configured_radius(self):
        trajectory = rounded_layer_mesh_trajectory((10, -20), 70, 15)

        self.assertTrue(all(
            math.hypot(x - 10, y + 20) <= 70 + 1.0e-9
            for x, y in trajectory
        ))

    def test_rounded_matrix_trajectory_uses_scanner_style_overscan_corners(self):
        trajectory = rounded_matrix_trajectory((0, 0), 1, 10, 20)

        self.assertTrue(any(abs(x) > 10 for x, _ in trajectory))
        self.assertTrue(all(math.hypot(x, y) <= 20 + 1.0e-9 for x, y in trajectory))

    def test_rounded_layer_trajectory_visits_every_fifteen_point_mesh_target(self):
        trajectory = rounded_layer_mesh_trajectory((0, 0), 7, 15)
        targets = {
            (xi - 7, yi - 7)
            for xi, yi in mesh_probe_indices(15, 15, circular=True)
        }

        def lies_on_path(point):
            for start, end in zip(trajectory, trajectory[1:]):
                dx, dy = end[0] - start[0], end[1] - start[1]
                length_squared = dx * dx + dy * dy
                if length_squared == 0:
                    continue
                ratio = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared
                if 0 <= ratio <= 1:
                    nearest_x = start[0] + ratio * dx
                    nearest_y = start[1] + ratio * dy
                    if math.hypot(point[0] - nearest_x, point[1] - nearest_y) < 1.0e-6:
                        return True
            return False

        self.assertTrue(all(lies_on_path(point) for point in targets))


if __name__ == "__main__":
    unittest.main()

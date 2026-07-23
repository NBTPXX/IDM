import unittest

from scanner_touch_mesh import (
    COMPENSATION_SECTION,
    CompensationProfile,
    difference_matrix,
    interpolate_matrix,
    matrix_range,
    needs_touch_retry,
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


if __name__ == "__main__":
    unittest.main()

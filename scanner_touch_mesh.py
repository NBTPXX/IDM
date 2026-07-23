"""Persistent data model for Scanner Touch mesh compensation."""

import math

COMPENSATION_SECTION = "scanner touch_mesh_compensation"
COMPENSATION_VERSION = 1


class CompensationProfile:
    def __init__(self, min_x, max_x, min_y, max_y, x_count, y_count, matrix):
        self.min_x = float(min_x)
        self.max_x = float(max_x)
        self.min_y = float(min_y)
        self.max_y = float(max_y)
        self.x_count = int(x_count)
        self.y_count = int(y_count)
        self.matrix = [[float(value) for value in row] for row in matrix]
        self.validate()

    def validate(self):
        if self.min_x >= self.max_x or self.min_y >= self.max_y:
            raise ValueError("compensation mesh bounds must have positive area")
        if self.x_count < 2 or self.y_count < 2:
            raise ValueError("compensation mesh requires at least two points per axis")
        if len(self.matrix) != self.y_count:
            raise ValueError("compensation row count does not match y_count")
        if any(len(row) != self.x_count for row in self.matrix):
            raise ValueError("compensation column count does not match x_count")

    def save(self, configfile):
        configfile.set(COMPENSATION_SECTION, "version", str(COMPENSATION_VERSION))
        configfile.set(COMPENSATION_SECTION, "enabled", "1")
        configfile.set(COMPENSATION_SECTION, "mesh_min", "%.6f,%.6f" % (self.min_x, self.min_y))
        configfile.set(COMPENSATION_SECTION, "mesh_max", "%.6f,%.6f" % (self.max_x, self.max_y))
        configfile.set(
            COMPENSATION_SECTION,
            "probe_count",
            "%d,%d" % (self.x_count, self.y_count),
        )
        for index, row in enumerate(self.matrix):
            configfile.set(
                COMPENSATION_SECTION,
                "row_%d" % (index,),
                ",".join("%.9f" % (value,) for value in row),
            )

    @classmethod
    def load(cls, config):
        if not config.has_section(COMPENSATION_SECTION):
            return None
        section = config.getsection(COMPENSATION_SECTION)
        if not section.getint("enabled", 0):
            return None
        if section.getint("version") != COMPENSATION_VERSION:
            raise ValueError("unsupported compensation profile version")

        min_x, min_y = _parse_values(section.get("mesh_min"), 2, "mesh_min")
        max_x, max_y = _parse_values(section.get("mesh_max"), 2, "mesh_max")
        x_count, y_count = _parse_int_values(
            section.get("probe_count"), 2, "probe_count"
        )
        matrix = [
            _parse_values(section.get("row_%d" % (index,)), x_count, "row_%d" % (index,))
            for index in range(y_count)
        ]
        return cls(min_x, max_x, min_y, max_y, x_count, y_count, matrix)

    @staticmethod
    def clear(configfile):
        configfile.set(COMPENSATION_SECTION, "version", str(COMPENSATION_VERSION))
        configfile.set(COMPENSATION_SECTION, "enabled", "0")


def _parse_values(value, expected_count, field_name):
    try:
        values = [float(item.strip()) for item in value.split(",")]
    except (AttributeError, ValueError) as error:
        raise ValueError("invalid compensation %s" % (field_name,)) from error
    if len(values) != expected_count:
        raise ValueError("invalid compensation %s length" % (field_name,))
    return values


def _parse_int_values(value, expected_count, field_name):
    values = _parse_values(value, expected_count, field_name)
    integers = [int(item) for item in values]
    if any(item != integer for item, integer in zip(values, integers)):
        raise ValueError("invalid compensation %s" % (field_name,))
    return integers


def difference_matrix(touch_matrix, scanner_matrix):
    if len(touch_matrix) != len(scanner_matrix) or any(
        len(touch_row) != len(scanner_row)
        for touch_row, scanner_row in zip(touch_matrix, scanner_matrix)
    ):
        raise ValueError("touch and scanner matrix dimensions differ")
    return [
        [touch_value - scanner_value for touch_value, scanner_value in zip(touch_row, scanner_row)]
        for touch_row, scanner_row in zip(touch_matrix, scanner_matrix)
    ]


def matrix_range(matrix):
    values = [value for row in matrix for value in row]
    if not values:
        raise ValueError("compensation matrix is empty")
    return min(values), max(values)


def interpolate_matrix(matrix, min_x, max_x, min_y, max_y, x_count, y_count, x, y):
    if x < min_x or x > max_x or y < min_y or y > max_y:
        return None
    if len(matrix) != y_count or any(len(row) != x_count for row in matrix):
        raise ValueError("matrix dimensions do not match interpolation geometry")

    x_index = (x - min_x) * (x_count - 1) / (max_x - min_x)
    y_index = (y - min_y) * (y_count - 1) / (max_y - min_y)
    x0 = min(int(x_index), x_count - 2)
    y0 = min(int(y_index), y_count - 2)
    x_fraction = x_index - x0
    y_fraction = y_index - y0

    lower = matrix[y0][x0] * (1 - x_fraction) + matrix[y0][x0 + 1] * x_fraction
    upper = matrix[y0 + 1][x0] * (1 - x_fraction) + matrix[y0 + 1][x0 + 1] * x_fraction
    return lower * (1 - y_fraction) + upper * y_fraction


def needs_touch_retry(touch_value, scanner_value, threshold):
    return abs(touch_value - scanner_value) - threshold > 1.0e-9


def apply_compensation(profile, matrix, min_x, max_x, min_y, max_y):
    y_count = len(matrix)
    x_count = len(matrix[0]) if y_count else 0
    if x_count < 2 or y_count < 2 or any(len(row) != x_count for row in matrix):
        raise ValueError("scanner mesh requires a rectangular grid with at least two points per axis")

    compensated = []
    uncovered = []
    for y_index, row in enumerate(matrix):
        y = min_y + (max_y - min_y) * y_index / (y_count - 1)
        compensated_row = []
        for x_index, scanner_value in enumerate(row):
            x = min_x + (max_x - min_x) * x_index / (x_count - 1)
            correction = interpolate_matrix(
                profile.matrix,
                profile.min_x,
                profile.max_x,
                profile.min_y,
                profile.max_y,
                profile.x_count,
                profile.y_count,
                x,
                y,
            )
            if correction is None:
                uncovered.append((x, y))
                compensated_row.append(scanner_value)
            else:
                compensated_row.append(scanner_value + correction)
        compensated.append(compensated_row)
    return compensated, uncovered


def align_matrices_at_center(matrix_a, matrix_b, min_x, max_x, min_y, max_y):
    y_count = len(matrix_a)
    x_count = len(matrix_a[0]) if y_count else 0
    if (
        x_count < 2
        or y_count < 2
        or len(matrix_b) != y_count
        or any(len(row) != x_count for row in matrix_a)
        or any(len(row) != x_count for row in matrix_b)
    ):
        raise ValueError("matrices require matching rectangular grids with at least two points per axis")

    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    center_a = interpolate_matrix(
        matrix_a, min_x, max_x, min_y, max_y, x_count, y_count, center_x, center_y
    )
    center_b = interpolate_matrix(
        matrix_b, min_x, max_x, min_y, max_y, x_count, y_count, center_x, center_y
    )
    return (
        [[value - center_a for value in row] for row in matrix_a],
        [[value - center_b for value in row] for row in matrix_b],
    )


def arc_retract_segments(start_xy, start_z, next_xy, retract_height, lift_speed, travel_speed):
    horizontal_distance = math.hypot(
        next_xy[0] - start_xy[0], next_xy[1] - start_xy[1]
    )
    radius = min(retract_height, horizontal_distance)
    if radius <= 0:
        return [([next_xy[0], next_xy[1], start_z + retract_height], lift_speed)]

    direction_x = (next_xy[0] - start_xy[0]) / horizontal_distance
    direction_y = (next_xy[1] - start_xy[1]) / horizontal_distance
    terminal_start = 2.0 * math.atan(travel_speed / lift_speed) - math.pi / 2.0
    if terminal_start > 0:
        base_count = max(1, int(math.ceil(terminal_start / (math.pi / 12.0))))
        angles = [terminal_start * index / base_count for index in range(1, base_count + 1)]
        angles.append(math.pi / 2.0)
    else:
        angles = [math.pi * index / 16.0 for index in range(1, 9)]
    segments = []
    previous_xy = start_xy
    previous_z = start_z
    for angle in angles:
        offset = radius * (1.0 - math.cos(angle))
        target_xy = [
            start_xy[0] + direction_x * offset,
            start_xy[1] + direction_y * offset,
        ]
        target_z = start_z + radius * math.sin(angle)
        xy_delta = math.hypot(
            target_xy[0] - previous_xy[0], target_xy[1] - previous_xy[1]
        )
        z_delta = target_z - previous_z
        segment_distance = math.hypot(xy_delta, z_delta)
        speed = lift_speed * segment_distance / z_delta if z_delta else travel_speed
        segments.append(([target_xy[0], target_xy[1], target_z], speed))
        previous_xy = target_xy
        previous_z = target_z

    if retract_height > radius:
        segments.append(([next_xy[0], next_xy[1], start_z + retract_height], lift_speed))
    elif horizontal_distance > radius:
        segments.append(([next_xy[0], next_xy[1], start_z + retract_height], travel_speed))
    return segments

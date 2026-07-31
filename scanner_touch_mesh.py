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


def parse_touch_retry_points(value):
    if not value or not value.strip():
        return []
    points = []
    for line_number, line in enumerate(value.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            x, y = (float(part.strip()) for part in line.split(","))
        except ValueError as error:
            raise ValueError(
                "touch_mesh_retry_points line %d must contain X,Y" % line_number
            ) from error
        if not math.isfinite(x) or not math.isfinite(y):
            raise ValueError(
                "touch_mesh_retry_points line %d must contain finite X,Y"
                % line_number
            )
        points.append((x, y))
    return points


def weighted_touch_correction(points, x, y, decay_start_radius=5.0):
    if not points:
        return 0.0
    nearest_distances = []
    for index, point in enumerate(points):
        distances = [
            math.hypot(point[0] - other[0], point[1] - other[1])
            for other_index, other in enumerate(points)
            if other_index != index
        ]
        nonzero_distances = [distance for distance in distances if distance >= 1.0e-9]
        nearest_distances.append(min(nonzero_distances) if nonzero_distances else 0.0)

    exact_values = []
    weighted_sum = 0.0
    total_weight = 0.0
    max_weight = 0.0
    for point, influence_distance in zip(points, nearest_distances):
        distance = math.hypot(x - point[0], y - point[1])
        if distance < 1.0e-9:
            exact_values.append(point[2])
            continue
        if influence_distance <= 0.0:
            continue
        decay_limit = (
            min(influence_distance, decay_start_radius * 2.0)
            if decay_start_radius > 0.0
            else influence_distance
        )
        if distance >= decay_limit:
            continue
        normalized_distance = distance / decay_limit
        weight = 1.0 - 0.2 * normalized_distance ** 2 - 0.8 * normalized_distance ** 3
        weighted_sum += point[2] * weight
        total_weight += weight
        max_weight = max(max_weight, weight)
    if exact_values:
        return sum(exact_values) / len(exact_values)
    if total_weight < 1.0e-9:
        return 0.0
    touch_correction = weighted_sum / total_weight
    return max_weight * touch_correction


def round_mesh_row_indices(count, row_index):
    """Return the X indices inside Klipper's square-sampled circular mesh."""
    if count < 3 or count % 2 == 0:
        raise ValueError("round mesh count must be an odd integer of at least three")
    center = count // 2
    y = row_index - center
    return [
        x_index
        for x_index in range(count)
        if math.hypot(x_index - center, y) <= center + 1.0e-9
    ]


def mesh_probe_indices(x_count, y_count, circular=False):
    """Return Klipper's bottom-to-top serpentine mesh probe order."""
    if circular and x_count != y_count:
        raise ValueError("circular mesh requires matching X and Y counts")
    points = []
    for y_index in range(y_count):
        x_indices = (
            round_mesh_row_indices(x_count, y_index)
            if circular
            else list(range(x_count))
        )
        if y_index % 2:
            x_indices.reverse()
        points.extend((x_index, y_index) for x_index in x_indices)
    return points


def round_lattice_orbits(count):
    """Return outer-to-inner four-point rotation orbits for a round mesh."""
    if count < 3 or count % 2 == 0:
        raise ValueError("round mesh count must be an odd integer of at least three")
    center = count // 2
    remaining = {
        (x - center, y - center)
        for y in range(count)
        for x in range(count)
        if (x != center or y != center)
        and math.hypot(x - center, y - center) <= center + 1.0e-9
    }
    orbits = []
    while remaining:
        point = next(iter(remaining))
        orbit = []
        current = point
        for _ in range(4):
            orbit.append(current)
            current = (-current[1], current[0])
        orbit_set = set(orbit)
        remaining.difference_update(orbit_set)
        start = max(orbit, key=lambda value: (value[0], -value[1]))
        start_index = orbit.index(start)
        orbits.append(tuple(orbit[start_index:] + orbit[:start_index]))
    return sorted(orbits, key=lambda orbit: math.hypot(*orbit[0]), reverse=True)


def centered_matrix_extent(points):
    """Return the half extent when points form a complete centered square."""
    if not points:
        return None
    extent = max(max(abs(x), abs(y)) for x, y in points)
    expected = {
        (x, y)
        for y in range(-extent, extent + 1)
        for x in range(-extent, extent + 1)
    }
    return extent if points == expected else None


def round_lattice_layers(count):
    """Peel outer X/Y boundary points until the remainder is a square matrix."""
    if count < 3 or count % 2 == 0:
        raise ValueError("round mesh count must be an odd integer of at least three")
    center = count // 2
    remaining = {
        (x - center, y - center)
        for y in range(count)
        for x in range(count)
        if math.hypot(x - center, y - center) <= center + 1.0e-9
    }
    layers = []
    while centered_matrix_extent(remaining) is None:
        outer_extent = max(max(abs(x), abs(y)) for x, y in remaining)
        layer = {
            point
            for point in remaining
            if max(abs(point[0]), abs(point[1])) == outer_extent
        }
        layers.append(layer)
        remaining.difference_update(layer)
    return layers, remaining


def arc_polyline(center, radius, start_angle, sweep_angle, max_sagitta=0.1):
    """Approximate a circular arc while bounding the chord sagitta error."""
    if radius <= 0:
        return [(center[0], center[1])]
    max_angle = 2.0 * math.acos(max(0.0, 1.0 - max_sagitta / radius))
    segments = max(1, int(math.ceil(abs(sweep_angle) / max_angle)))
    return [
        (
            center[0] + radius * math.cos(start_angle + sweep_angle * index / segments),
            center[1] + radius * math.sin(start_angle + sweep_angle * index / segments),
        )
        for index in range(segments + 1)
    ]


def rounded_square_path(origin, half_extent, side_half, max_radius, max_sagitta=0.1):
    """Return a rounded layer path through its four X/Y boundary sides."""
    outer_radius = math.hypot(half_extent, side_half)
    if outer_radius > max_radius + 1.0e-9:
        raise ValueError("rounded square exceeds the configured bed radius")

    def rotate(point, turns):
        x, y = point
        for _ in range(turns):
            x, y = -y, x
        return (origin[0] + x, origin[1] + y)

    points = [(origin[0] + half_extent, origin[1] - side_half)]
    points.append((origin[0] + half_extent, origin[1] + side_half))
    start_angle = math.atan2(side_half, half_extent)
    corner_path = arc_polyline(
        (0.0, 0.0),
        outer_radius,
        start_angle,
        math.pi / 2.0 - 2.0 * start_angle,
        max_sagitta,
    )[1:]
    side_endpoints = [
        (-side_half, half_extent),
        (-half_extent, -side_half),
        (side_half, -half_extent),
    ]
    for index in range(4):
        points.extend(rotate(point, index) for point in corner_path)
        if index < len(side_endpoints):
            points.append(rotate(side_endpoints[index], 0))
    return points


def rounded_matrix_trajectory(origin, matrix_extent, step, max_radius, max_sagitta=0.1):
    """Build the rounded overscan serpentine used by rectangular Scanner meshes."""
    if matrix_extent == 0:
        return [origin]

    bound = matrix_extent * step

    def build_path(overscan):
        corner_radius = min(step / 2.0, overscan)
        points = []
        for row in range(matrix_extent * 2 + 1):
            y = -bound + row * step
            even = row % 2 == 0
            start = (-bound, y) if even else (bound, y)
            end = (bound, y) if even else (-bound, y)
            if row and corner_radius > 0:
                previous_y = y - step
                if even:
                    center_x = -bound - overscan + corner_radius
                    arcs = [
                        ((center_x, previous_y + corner_radius), -math.pi / 2.0, -math.pi / 2.0),
                        ((center_x, y - corner_radius), math.pi, -math.pi / 2.0),
                    ]
                else:
                    center_x = bound + overscan - corner_radius
                    arcs = [
                        ((center_x, previous_y + corner_radius), -math.pi / 2.0, math.pi / 2.0),
                        ((center_x, y - corner_radius), 0.0, math.pi / 2.0),
                    ]
                for center, angle, sweep in arcs:
                    points.extend(
                        arc_polyline(
                            (origin[0] + center[0], origin[1] + center[1]),
                            corner_radius,
                            angle,
                            sweep,
                            max_sagitta,
                        )
                    )
            points.append((origin[0] + start[0], origin[1] + start[1]))
            points.append((origin[0] + end[0], origin[1] + end[1]))
        return points

    maximum_overscan = step / 2.0
    path = build_path(maximum_overscan)
    if all(
        math.hypot(x - origin[0], y - origin[1]) <= max_radius + 1.0e-9
        for x, y in path
    ):
        return path
    lower, upper = 0.0, maximum_overscan
    for _ in range(32):
        middle = (lower + upper) / 2.0
        path = build_path(middle)
        if all(
            math.hypot(x - origin[0], y - origin[1]) <= max_radius + 1.0e-9
            for x, y in path
        ):
            lower = middle
        else:
            upper = middle
    return build_path(lower)


def rounded_layer_mesh_trajectory(origin, radius, count, max_sagitta=0.1):
    """Scan outer X/Y layers, then finish the remaining centered square matrix."""
    center = count // 2
    step = radius / center
    layers, matrix_points = round_lattice_layers(count)
    trajectory = []
    for layer in layers:
        max_component = max(max(abs(x), abs(y)) for x, y in layer)
        side_half = max(min(abs(x), abs(y)) for x, y in layer)
        half_extent = max_component * step
        trajectory.extend(
            rounded_square_path(
                origin,
                half_extent,
                side_half * step,
                radius,
                max_sagitta,
            )
        )
    matrix_extent = centered_matrix_extent(matrix_points)
    trajectory.extend(
        rounded_matrix_trajectory(
            origin,
            matrix_extent,
            step,
            radius,
            max_sagitta,
        )
    )
    return trajectory


def tangent_connector_polyline(start, start_tangent, end, end_tangent, segments=12):
    """Approximate a cubic curve that is tangent to both adjacent arcs."""
    distance = math.hypot(end[0] - start[0], end[1] - start[1])
    handle = distance / 3.0
    control_a = (start[0] + start_tangent[0] * handle, start[1] + start_tangent[1] * handle)
    control_b = (end[0] - end_tangent[0] * handle, end[1] - end_tangent[1] * handle)
    return [
        (
            (1 - t) ** 3 * start[0]
            + 3 * (1 - t) ** 2 * t * control_a[0]
            + 3 * (1 - t) * t**2 * control_b[0]
            + t**3 * end[0],
            (1 - t) ** 3 * start[1]
            + 3 * (1 - t) ** 2 * t * control_a[1]
            + 3 * (1 - t) * t**2 * control_b[1]
            + t**3 * end[1],
        )
        for t in (index / segments for index in range(segments + 1))
    ]


def nearest_orbit_point_in_direction(points, previous_angle, direction):
    """Choose the next target with the smallest angular advance."""
    if direction not in (-1, 1):
        raise ValueError("direction must be -1 or 1")
    angles = [math.atan2(point[1], point[0]) for point in points]
    advances = [
        (angle - previous_angle) % (2.0 * math.pi)
        if direction > 0
        else (previous_angle - angle) % (2.0 * math.pi)
        for angle in angles
    ]
    return min(range(len(points)), key=lambda index: advances[index])


def round_mesh_trajectory(origin, radius, count, max_sagitta=0.1, direction=1):
    """Build an outer-to-center, 270-degree-per-orbit round mesh path."""
    if direction not in (-1, 1):
        raise ValueError("direction must be -1 or 1")
    center = count // 2
    step = radius / center
    trajectory = []
    travel_direction = direction
    orbits = [
        [
            (origin[0] + dx * step, origin[1] + dy * step)
            for dx, dy in orbit
        ]
        for orbit in round_lattice_orbits(count)
    ]
    start_point = orbits[0][0]
    for orbit_index, points in enumerate(orbits):
        start_angle = math.atan2(
            start_point[1] - origin[1], start_point[0] - origin[0]
        )
        orbit_radius = math.hypot(
            start_point[0] - origin[0], start_point[1] - origin[1]
        )
        for point_index in range(3):
            angle = start_angle + travel_direction * point_index * math.pi / 2.0
            arc = arc_polyline(
                origin,
                orbit_radius,
                angle,
                travel_direction * math.pi / 2.0,
                max_sagitta,
            )
            trajectory.extend(arc[1 if trajectory else 0 :])
        end_angle = start_angle + travel_direction * 3.0 * math.pi / 2.0
        if orbit_index + 1 < len(orbits):
            next_points = orbits[orbit_index + 1]
            local_next_points = [
                (point[0] - origin[0], point[1] - origin[1])
                for point in next_points
            ]
            next_radius = math.hypot(*local_next_points[0])
            if math.isclose(orbit_radius, next_radius, abs_tol=1.0e-9):
                point_angles = [
                    math.atan2(point[1], point[0]) for point in local_next_points
                ]
                point_advances = [
                    (angle - end_angle) % (2.0 * math.pi)
                    if travel_direction > 0
                    else (end_angle - angle) % (2.0 * math.pi)
                    for angle in point_angles
                ]
                next_index = min(range(4), key=lambda index: point_advances[index])
                trajectory.extend(
                    arc_polyline(
                        origin,
                        orbit_radius,
                        end_angle,
                        point_advances[next_index] * travel_direction,
                        max_sagitta,
                    )[1:]
                )
            else:
                point_angles = [
                    math.atan2(point[1], point[0]) for point in local_next_points
                ]
                point_advances = [
                    (angle - end_angle) % (2.0 * math.pi)
                    if travel_direction > 0
                    else (end_angle - angle) % (2.0 * math.pi)
                    for angle in point_angles
                ]
                next_index = min(range(4), key=lambda index: point_advances[index])
                tangent_angle = point_angles[next_index]
                extra_sweep = point_advances[next_index] * travel_direction
                if abs(extra_sweep) > 1.0e-9:
                    trajectory.extend(
                        arc_polyline(
                            origin, orbit_radius, end_angle, extra_sweep, max_sagitta
                        )[1:]
                    )
                connector_radius = (orbit_radius - next_radius) / 2.0
                connector_center_radius = (orbit_radius + next_radius) / 2.0
                connector_center = (
                    origin[0] + connector_center_radius * math.cos(tangent_angle),
                    origin[1] + connector_center_radius * math.sin(tangent_angle),
                )
                trajectory.extend(
                    arc_polyline(
                        connector_center,
                        connector_radius,
                        tangent_angle,
                        travel_direction * math.pi,
                        max_sagitta,
                    )[1:]
                )
                # A single circular connector reverses the tangent direction
                # at its second contact with the next concentric ring.
                travel_direction *= -1
            start_point = next_points[next_index]

    trajectory.append((origin[0], origin[1]))
    return trajectory


def fill_round_mesh_edges(matrix, valid_rows):
    """Pad a circular mesh into Klipper's square matrix representation."""
    filled = [list(row) for row in matrix]
    for row, valid_indices in zip(filled, valid_rows):
        if not valid_indices:
            raise ValueError("round mesh row has no valid probe coordinates")
        first, last = valid_indices[0], valid_indices[-1]
        if (
            row[first] is None
            or row[last] is None
            or not math.isfinite(row[first])
            or not math.isfinite(row[last])
        ):
            raise ValueError("round mesh row is missing an edge measurement")
        for index in range(first):
            row[index] = row[first]
        for index in range(last + 1, len(row)):
            row[index] = row[last]
    return filled


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
    """Shift the Touch matrix to the Scanner center without altering Scanner Z."""
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
        [[value + center_b - center_a for value in row] for row in matrix_a],
        [list(row) for row in matrix_b],
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

"""Persistent data model for Scanner Touch mesh compensation."""

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

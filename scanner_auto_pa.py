# Scanner-based automatic Pressure Advance calibration.
import csv
import math
import os
import statistics


def volumetric_flow_to_e_distance(flow, duration, filament_diameter):
    area = math.pi * (filament_diameter / 2.0) ** 2
    return flow * duration / area


def volumetric_flow_to_line_distance(flow, duration, line_width, layer_height):
    return flow * duration / (line_width * layer_height)


def build_bed_line_plan(start_x, start_y, line_length, line_spacing,
                        candidate_count, cycles):
    plan = []
    row = 0
    for _ in range(candidate_count):
        candidate_lines = []
        for _ in range(cycles):
            left_to_right = row % 2 == 0
            candidate_lines.append({
                "start_x": start_x if left_to_right else start_x + line_length,
                "end_x": start_x + line_length if left_to_right else start_x,
                "y": start_y + row * line_spacing,
                "direction": 1.0 if left_to_right else -1.0,
            })
            row += 1
        plan.append(candidate_lines)
    return plan


def pressure_proxy(baseline_freq, freq):
    # This Scanner's frequency falls as nozzle back-pressure increases.
    return baseline_freq - freq


class ScannerAutoPA:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object("gcode")
        self.scanner = self.printer.lookup_object("scanner")
        self.filament_diameter = config.getfloat("filament_diameter", 1.75, above=0.0)
        self.baseline_time = config.getfloat("baseline_time", 1.0, above=0.0)
        self.min_samples = config.getint("min_samples", 20, minval=1)
        self.gcode.register_command(
            "SCANNER_AUTO_PA", self.cmd_SCANNER_AUTO_PA,
            desc="Calibrate Pressure Advance using Scanner frequency data",
        )
        self.gcode.register_command(
            "SCANNER_AUTO_PA_DEBUG", self.cmd_SCANNER_AUTO_PA_DEBUG,
            desc="Capture one Scanner Pressure Advance debug cycle",
        )

    def cmd_SCANNER_AUTO_PA(self, gcmd):
        toolhead = self.printer.lookup_object("toolhead")
        self._verify_ready(toolhead, gcmd)
        settings = self._settings(gcmd)
        extruder = toolhead.get_extruder()
        eventtime = self.printer.get_reactor().monotonic()
        original_pa = extruder.get_status(eventtime).get("pressure_advance", 0.0)
        original_accel = toolhead.get_status(eventtime)["max_accel"]
        results = []
        k_values = self._k_values(settings)
        settings["line_plan"] = self._plan_bed_lines(
            toolhead, gcmd, settings, len(k_values)
        )

        try:
            self.gcode.run_script_from_command(
                "SET_VELOCITY_LIMIT ACCEL=%.3f" % (settings["accel"],)
            )
            for candidate_index, k in enumerate(k_values):
                result = self._run_candidate(
                    toolhead, k, settings, candidate_index
                )
                results.append(result)
                if result["valid"]:
                    gcmd.respond_info(
                        "SCANNER_AUTO_PA K=%.5f samples=%d score=%.6f "
                        "overshoot=%.6f undershoot=%.6f slope=%.6f area=%.6f"
                        % (
                            k, result["sample_count"], result["score"],
                            result["overshoot"], result["undershoot"],
                            result["plateau_slope"], result["area"],
                        )
                    )
                else:
                    gcmd.respond_info(
                        "SCANNER_AUTO_PA K=%.5f invalid: %s"
                        % (k, result["reason"])
                    )

            valid_results = [result for result in results if result["valid"]]
            if not valid_results:
                raise gcmd.error("SCANNER_AUTO_PA collected no valid candidates")
            best = min(valid_results, key=lambda result: result["score"])
            if settings["export"]:
                self._export(settings["export"], results)
            if settings["apply"]:
                self._set_pa(best["k"])
                applied = " applied"
            else:
                self._set_pa(original_pa)
                applied = ""
            gcmd.respond_info(
                "SCANNER_AUTO_PA recommended K=%.5f score=%.6f%s"
                % (best["k"], best["score"], applied)
            )
        except Exception:
            self._set_pa(original_pa)
            raise
        finally:
            self.gcode.run_script_from_command(
                "SET_VELOCITY_LIMIT ACCEL=%.3f" % (original_accel,)
            )

    def cmd_SCANNER_AUTO_PA_DEBUG(self, gcmd):
        toolhead = self.printer.lookup_object("toolhead")
        self._verify_ready(toolhead, gcmd)
        settings = self._settings(gcmd)
        settings["cycles"] = gcmd.get_int("CYCLES", 1, minval=1)
        settings["line_plan"] = self._plan_bed_lines(toolhead, gcmd, settings, 1)
        filename = os.path.basename(gcmd.get("FILENAME", "scanner-auto-pa-debug.csv"))
        extruder = toolhead.get_extruder()
        eventtime = self.printer.get_reactor().monotonic()
        original_pa = extruder.get_status(eventtime).get("pressure_advance", 0.0)
        original_accel = toolhead.get_status(eventtime)["max_accel"]
        k = gcmd.get_float("K", original_pa, minval=0.0)
        try:
            self.gcode.run_script_from_command(
                "SET_VELOCITY_LIMIT ACCEL=%.3f" % (settings["accel"],)
            )
            baseline, samples = self._capture_candidate(toolhead, k, settings, 0)
            result = self._analyse_candidate(k, baseline, samples)
            if not result["valid"]:
                raise gcmd.error("SCANNER_AUTO_PA_DEBUG: " + result["reason"])
            self._export_debug(filename, baseline, samples)
            gcmd.respond_info(
                "SCANNER_AUTO_PA_DEBUG wrote /tmp/%s with %d samples"
                % (filename, result["sample_count"])
            )
        finally:
            self._set_pa(original_pa)
            self.gcode.run_script_from_command(
                "SET_VELOCITY_LIMIT ACCEL=%.3f" % (original_accel,)
            )

    def _verify_ready(self, toolhead, gcmd):
        if self.scanner.model is None:
            raise gcmd.error("SCANNER_AUTO_PA requires a loaded Scanner model")
        homed_axes = toolhead.get_status(
            self.printer.get_reactor().monotonic()
        )["homed_axes"]
        if not all(axis in homed_axes for axis in ("x", "y", "z")):
            raise gcmd.error("SCANNER_AUTO_PA requires homed X, Y, and Z axes")
        if toolhead.get_extruder() is None:
            raise gcmd.error("SCANNER_AUTO_PA requires an active extruder")

    def _settings(self, gcmd):
        start_k = gcmd.get_float("START_K", 0.0, minval=0.0)
        end_k = gcmd.get_float("END_K", 0.1, minval=start_k)
        step = gcmd.get_float("STEP", 0.002, above=0.0)
        cycles = gcmd.get_int("CYCLES", 1, minval=1)
        low_flow = gcmd.get_float("LOW_FLOW", 1.92, above=0.0)
        high_flow = gcmd.get_float("HIGH_FLOW", 19.24, above=0.0)
        low_time = gcmd.get_float("LOW_TIME", 1.0, above=0.0)
        high_time = gcmd.get_float("HIGH_TIME", 0.25, above=0.0)
        export = gcmd.get("EXPORT", "").strip()
        return {
            "start_k": start_k,
            "end_k": end_k,
            "step": step,
            "cycles": cycles,
            "low_flow": low_flow,
            "high_flow": high_flow,
            "low_time": low_time,
            "high_time": high_time,
            "baseline_time": self.baseline_time,
            "layer_height": gcmd.get_float("LAYER_HEIGHT", 0.2, above=0.0),
            "line_width": gcmd.get_float("LINE_WIDTH", 0.45, above=0.0),
            "line_spacing": gcmd.get_float("LINE_SPACING", 1.0, above=0.0),
            "z_hop": gcmd.get_float("Z_HOP", 2.0, above=0.0),
            "travel_speed": gcmd.get_float("TRAVEL_SPEED", 100.0, above=0.0),
            "z_speed": gcmd.get_float("Z_SPEED", 10.0, above=0.0),
            "accel": gcmd.get_float("ACCEL", 5000.0, above=0.0),
            "apply": gcmd.get_int("APPLY", 0, minval=0) == 1,
            "export": os.path.basename(export),
        }

    def _k_values(self, settings):
        count = int(round((settings["end_k"] - settings["start_k"]) / settings["step"]))
        return [settings["start_k"] + index * settings["step"] for index in range(count + 1)]

    def _plan_bed_lines(self, toolhead, gcmd, settings, candidate_count):
        eventtime = self.printer.get_reactor().monotonic()
        status = toolhead.get_kinematics().get_status(eventtime)
        axis_minimum = status["axis_minimum"]
        axis_maximum = status["axis_maximum"]
        scanner_offset = getattr(self.scanner, "offset", {})
        offset_x = scanner_offset.get("x", 0.0)
        offset_y = scanner_offset.get("y", 0.0)
        usable_x_min = max(axis_minimum[0], axis_minimum[0] - offset_x)
        usable_x_max = min(axis_maximum[0], axis_maximum[0] - offset_x)
        usable_y_min = max(axis_minimum[1], axis_minimum[1] - offset_y)
        usable_y_max = min(axis_maximum[1], axis_maximum[1] - offset_y)
        start_x = gcmd.get_float("START_X", usable_x_min + 5.0)
        start_y = gcmd.get_float("START_Y", usable_y_min + 5.0)

        if settings["line_spacing"] < settings["line_width"]:
            raise gcmd.error("SCANNER_AUTO_PA LINE_SPACING must be at least LINE_WIDTH")
        segment_distances = [
            volumetric_flow_to_line_distance(
                flow, duration, settings["line_width"], settings["layer_height"]
            )
            for flow, duration in (
                (settings["low_flow"], settings["low_time"]),
                (settings["high_flow"], settings["high_time"]),
                (settings["low_flow"], settings["low_time"]),
            )
        ]
        settings["segment_distances"] = segment_distances
        line_length = sum(segment_distances)
        row_count = candidate_count * settings["cycles"]
        end_x = start_x + line_length
        end_y = start_y + (row_count - 1) * settings["line_spacing"]
        travel_z = settings["layer_height"] + settings["z_hop"]
        if start_x < usable_x_min or end_x > usable_x_max:
            raise gcmd.error(
                "SCANNER_AUTO_PA lines require X %.3f..%.3f; usable X is %.3f..%.3f"
                % (start_x, end_x, usable_x_min, usable_x_max)
            )
        if start_y < usable_y_min or end_y > usable_y_max:
            raise gcmd.error(
                "SCANNER_AUTO_PA lines require Y %.3f..%.3f; usable Y is %.3f..%.3f"
                % (start_y, end_y, usable_y_min, usable_y_max)
            )
        if settings["layer_height"] < axis_minimum[2] or travel_z > axis_maximum[2]:
            raise gcmd.error(
                "SCANNER_AUTO_PA Z range %.3f..%.3f exceeds machine limits %.3f..%.3f"
                % (
                    settings["layer_height"], travel_z,
                    axis_minimum[2], axis_maximum[2],
                )
            )
        settings["travel_z"] = travel_z
        return build_bed_line_plan(
            start_x, start_y, line_length, settings["line_spacing"],
            candidate_count, settings["cycles"]
        )

    def _run_candidate(self, toolhead, k, settings, candidate_index):
        baseline, samples = self._capture_candidate(
            toolhead, k, settings, candidate_index
        )
        return self._analyse_candidate(k, baseline, samples)

    def _capture_candidate(self, toolhead, k, settings, candidate_index):
        baseline = []
        samples = []
        capture_target = [baseline]

        def capture(sample):
            freq = sample.get("freq")
            if freq is not None:
                capture_target[0].append({
                    "time": sample.get("time"),
                    "data": sample.get("data"),
                    "freq": freq,
                    "temp": sample.get("temp"),
                    "pos": sample.get("pos"),
                })

        lines = settings["line_plan"][candidate_index]
        self._set_pa(k)
        self.gcode.run_script_from_command("SAVE_GCODE_STATE NAME=SCANNER_AUTO_PA")
        self.gcode.run_script_from_command("G90\nM83")
        try:
            for line_index, line in enumerate(lines):
                self._move_to_bed_line(line, settings)
                toolhead.wait_moves()
                with self.scanner.streaming_session(capture, latency=1):
                    if line_index == 0:
                        self.gcode.run_script_from_command(
                            "G4 P%d" % int(settings["baseline_time"] * 1000)
                        )
                        toolhead.wait_moves()
                        capture_target[0] = samples
                    self._print_bed_line(line, settings)
                    toolhead.wait_moves()
        finally:
            self.gcode.run_script_from_command(
                "G1 Z%.5f F%.3f"
                % (settings["travel_z"], settings["z_speed"] * 60.0)
            )
            self.gcode.run_script_from_command(
                "RESTORE_GCODE_STATE NAME=SCANNER_AUTO_PA"
            )
        return baseline, samples

    def _move_to_bed_line(self, line, settings):
        travel_feed = settings["travel_speed"] * 60.0
        z_feed = settings["z_speed"] * 60.0
        self.gcode.run_script_from_command(
            "G1 Z%.5f F%.3f" % (settings["travel_z"], z_feed)
        )
        self.gcode.run_script_from_command(
            "G1 X%.5f Y%.5f F%.3f"
            % (line["start_x"], line["y"], travel_feed)
        )
        self.gcode.run_script_from_command(
            "G1 Z%.5f F%.3f" % (settings["layer_height"], z_feed)
        )

    def _print_bed_line(self, line, settings):
        flow_steps = (
            (settings["low_flow"], settings["low_time"]),
            (settings["high_flow"], settings["high_time"]),
            (settings["low_flow"], settings["low_time"]),
        )
        target_x = line["start_x"]
        for (flow, duration), distance in zip(
                flow_steps, settings["segment_distances"]):
            target_x += line["direction"] * distance
            e_distance = volumetric_flow_to_e_distance(
                flow, duration, self.filament_diameter
            )
            feed = distance / duration * 60.0
            self.gcode.run_script_from_command(
                "G1 X%.5f E%.6f F%.3f"
                % (target_x, e_distance, feed)
            )

    def _analyse_candidate(self, k, baseline, samples):
        if len(baseline) < self.min_samples or len(samples) < self.min_samples:
            return self._invalid_result(k, len(samples), "insufficient Scanner samples")
        baseline_freq = statistics.median(sample["freq"] for sample in baseline)
        proxy = [pressure_proxy(baseline_freq, sample["freq"]) for sample in samples]
        sample_count = len(proxy)
        quarter = max(1, sample_count // 4)
        overshoot = max(proxy)
        undershoot = abs(min(proxy))
        plateau_slope = abs(
            statistics.mean(proxy[-quarter:]) - statistics.mean(proxy[:quarter])
        )
        area = statistics.mean(abs(value) for value in proxy)
        score = overshoot ** 2 + undershoot ** 2 + plateau_slope ** 2 + area ** 2
        return {
            "k": k,
            "valid": True,
            "reason": "",
            "sample_count": sample_count,
            "overshoot": overshoot,
            "undershoot": undershoot,
            "plateau_slope": plateau_slope,
            "area": area,
            "score": score,
        }

    def _invalid_result(self, k, sample_count, reason):
        return {
            "k": k, "valid": False, "reason": reason,
            "sample_count": sample_count, "overshoot": 0.0,
            "undershoot": 0.0, "plateau_slope": 0.0,
            "area": 0.0, "score": float("inf"),
        }

    def _set_pa(self, value):
        self.gcode.run_script_from_command(
            "SET_PRESSURE_ADVANCE ADVANCE=%.7f" % (value,)
        )

    def _export(self, filename, results):
        if not filename:
            return
        path = os.path.join("/tmp", filename)
        with open(path, "w", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=sorted(results[0].keys()))
            writer.writeheader()
            writer.writerows(results)

    def _export_debug(self, filename, baseline, samples):
        baseline_freq = statistics.median(sample["freq"] for sample in baseline)
        path = os.path.join("/tmp", filename)
        fields = [
            "phase", "time", "data", "freq", "pressure_proxy", "temp",
            "pos_x", "pos_y", "pos_z",
        ]
        with open(path, "w", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            for phase, source in (("baseline", baseline), ("test", samples)):
                for sample in source:
                    pos = sample.get("pos") or (None, None, None)
                    writer.writerow({
                        "phase": phase,
                        "time": sample.get("time"),
                        "data": sample.get("data"),
                        "freq": sample["freq"],
                        "pressure_proxy": pressure_proxy(baseline_freq, sample["freq"]),
                        "temp": sample.get("temp"),
                        "pos_x": pos[0], "pos_y": pos[1], "pos_z": pos[2],
                    })


def load_config(config):
    return ScannerAutoPA(config)

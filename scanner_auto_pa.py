# Scanner-based automatic Pressure Advance calibration.
import csv
import math
import os
import statistics


def volumetric_flow_to_e_distance(flow, duration, filament_diameter):
    area = math.pi * (filament_diameter / 2.0) ** 2
    return flow * duration / area


def pressure_proxy(baseline_freq, freq):
    # This Scanner's frequency falls as nozzle back-pressure increases.
    return baseline_freq - freq


class ScannerAutoPA:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object("gcode")
        self.scanner = self.printer.lookup_object("scanner")
        self.filament_diameter = config.getfloat("filament_diameter", 1.75, above=0.0)
        self.xy_amplitude = config.getfloat("xy_amplitude", 1.0, above=0.0)
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

        try:
            self.gcode.run_script_from_command(
                "SET_VELOCITY_LIMIT ACCEL=%.3f" % (settings["accel"],)
            )
            for k in self._k_values(settings):
                result = self._run_candidate(toolhead, k, settings)
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
            baseline, samples = self._capture_candidate(toolhead, k, settings)
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
        cycles = gcmd.get_int("CYCLES", 14, minval=1)
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
            "accel": gcmd.get_float("ACCEL", 5000.0, above=0.0),
            "apply": gcmd.get_int("APPLY", 0, minval=0) == 1,
            "export": os.path.basename(export),
        }

    def _k_values(self, settings):
        count = int(round((settings["end_k"] - settings["start_k"]) / settings["step"]))
        return [settings["start_k"] + index * settings["step"] for index in range(count + 1)]

    def _run_candidate(self, toolhead, k, settings):
        baseline, samples = self._capture_candidate(toolhead, k, settings)
        return self._analyse_candidate(k, baseline, samples)

    def _capture_candidate(self, toolhead, k, settings):
        samples = []

        def capture(sample):
            freq = sample.get("freq")
            if freq is not None:
                samples.append({
                    "time": sample.get("time"),
                    "data": sample.get("data"),
                    "freq": freq,
                    "temp": sample.get("temp"),
                    "pos": sample.get("pos"),
                })

        self._set_pa(k)
        with self.scanner.streaming_session(capture, latency=1):
            self.gcode.run_script_from_command("G4 P%d" % int(settings["baseline_time"] * 1000))
            toolhead.wait_moves()
            baseline_count = len(samples)
            self._run_bursts(toolhead, settings)
            toolhead.wait_moves()
        return samples[:baseline_count], samples[baseline_count:]

    def _run_bursts(self, toolhead, settings):
        self.gcode.run_script_from_command("SAVE_GCODE_STATE NAME=SCANNER_AUTO_PA")
        self.gcode.run_script_from_command("G91\nM83")
        try:
            for _ in range(settings["cycles"]):
                direction = 1.0
                for flow, duration in (
                    (settings["low_flow"], settings["low_time"]),
                    (settings["high_flow"], settings["high_time"]),
                    (settings["low_flow"], settings["low_time"]),
                ):
                    e_distance = volumetric_flow_to_e_distance(
                        flow, duration, self.filament_diameter
                    )
                    feed = self.xy_amplitude / duration * 60.0
                    self.gcode.run_script_from_command(
                        "G1 X%.5f E%.6f F%.3f"
                        % (direction * self.xy_amplitude, e_distance, feed)
                    )
                    direction *= -1.0
                self.gcode.run_script_from_command(
                    "G1 X%.5f F%.3f" % (direction * self.xy_amplitude, 600.0)
                )
        finally:
            self.gcode.run_script_from_command("RESTORE_GCODE_STATE NAME=SCANNER_AUTO_PA")

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

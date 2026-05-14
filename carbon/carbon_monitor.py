import json
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import pynvml
from codecarbon import EmissionsTracker


class CarbonMonitor:
    def __init__(
        self,
        ci_value=350.0,
        enabled=True,
        gpu_index=0,
        sample_interval=0.1,
        log_path=None,
    ):
        self.ci_value = ci_value
        self.enabled = enabled
        self.gpu_index = gpu_index
        self.sample_interval = sample_interval
        self.log_path = Path(log_path) if log_path else None
        self._gpu_handle = None

        if not self.enabled:
            return

        try:
            pynvml.nvmlInit()
            self._gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(self.gpu_index)
        except pynvml.NVMLError:
            self._gpu_handle = None

    @classmethod
    def from_config(cls, cfg):
        return cls(
            ci_value=cfg.CARBON_INTENSITY_G_PER_KWH,
            enabled=cfg.CARBON_MONITOR_ENABLED,
            gpu_index=cfg.CARBON_GPU_INDEX,
            sample_interval=cfg.CARBON_SAMPLE_INTERVAL,
            log_path=cfg.CARBON_LOG_PATH,
        )

    def _build_tracker(self):
        tracker_kwargs = {
            "save_to_file": False,
            "save_to_api": False,
            "save_to_logger": False,
            "log_level": "error",
            "measure_power_secs": self.sample_interval,
            "allow_multiple_runs": False,
        }
        if self._gpu_handle is not None:
            tracker_kwargs["gpu_ids"] = [self.gpu_index]
        return EmissionsTracker(**tracker_kwargs)

    def _sample_gpu_power(self, stop_event, power_records):
        if self._gpu_handle is None:
            return
        while not stop_event.is_set():
            try:
                power_mw = pynvml.nvmlDeviceGetPowerUsage(self._gpu_handle)
                power_records.append(power_mw / 1000.0)
            except pynvml.NVMLError:
                break
            time.sleep(self.sample_interval)

    def _zero_metrics(self, stage_name, extra):
        metrics = {
            "stage": stage_name,
            "duration_sec": 0.0,
            "energy_kwh": 0.0,
            "co2_g": 0.0,
            "peak_power_W": 0.0,
            "avg_power_W": 0.0,
        }
        if extra:
            metrics["extra"] = extra
        return metrics

    def _write_metrics(self, metrics):
        if not self.log_path:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(metrics, ensure_ascii=False) + "\n")

    @contextmanager
    def track(self, stage_name, extra=None):
        if not self.enabled:
            state = {"metrics": self._zero_metrics(stage_name, extra)}
            yield state
            return

        power_records = []
        stop_event = threading.Event()
        monitor_thread = threading.Thread(
            target=self._sample_gpu_power,
            args=(stop_event, power_records),
            daemon=True,
        )
        tracker = self._build_tracker()

        monitor_thread.start()
        tracker.start()
        start_time = time.time()
        state = {"metrics": None}

        try:
            yield state
        finally:
            duration = time.time() - start_time
            tracker.stop()
            stop_event.set()
            monitor_thread.join()

            emissions = tracker.final_emissions_data
            energy_kwh = getattr(emissions, "energy_consumed", 0.0) or 0.0
            metrics = {
                "stage": stage_name,
                "duration_sec": round(duration, 4),
                "energy_kwh": energy_kwh,
                "co2_g": round(energy_kwh * self.ci_value, 4),
                "peak_power_W": round(max(power_records), 2) if power_records else 0.0,
                "avg_power_W": round(sum(power_records) / len(power_records), 2) if power_records else 0.0,
            }
            if extra:
                metrics["extra"] = extra
            state["metrics"] = metrics
            self._write_metrics(metrics)

    def run(self, stage_name, func, *args, extra=None, **kwargs):
        with self.track(stage_name, extra=extra) as state:
            result = func(*args, **kwargs)
        return result, state["metrics"]

    def measure(self, stage_name, extra=None):
        def decorator(func):
            def wrapper(*args, **kwargs):
                result, metrics = self.run(stage_name, func, *args, extra=extra, **kwargs)
                return result, metrics
            return wrapper
        return decorator

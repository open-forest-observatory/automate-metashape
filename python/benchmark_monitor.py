"""
Benchmark monitoring for Metashape API calls.

Provides a context manager that wraps API calls and logs:
- Duration
- Average CPU utilization
- Average GPU utilization

Integrates with the existing log file and adds a machine-readable YAML format.
"""

import threading
import time
from contextlib import contextmanager

import psutil
import yaml

# Try to import pynvml for GPU monitoring
try:
    import pynvml

    PYNVML_AVAILABLE = True
except ImportError:
    PYNVML_AVAILABLE = False


class BenchmarkMonitor:
    """Monitor and log performance metrics for Metashape API calls."""

    def __init__(self, log_file: str, yaml_log_path: str):
        """
        Initialize the benchmark monitor.

        Args:
            log_file: Path to existing human-readable log file (appends to it)
            yaml_log_path: Path for machine-readable YAML metrics file
        """
        self.log_file = log_file
        self.yaml_log_path = yaml_log_path

        # GPU initialization
        self.gpu_available = False
        self.gpu_count = 0
        if PYNVML_AVAILABLE:
            try:
                pynvml.nvmlInit()
                self.gpu_count = pynvml.nvmlDeviceGetCount()
                self.gpu_available = self.gpu_count > 0
            except pynvml.NVMLError:
                pass

    def _format_duration(self, seconds: float) -> str:
        """Format duration as HH:MM:SS."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _get_gpu_utilization(self) -> float:
        """Get average GPU utilization across all GPUs."""
        if not self.gpu_available:
            return None

        try:
            total_util = 0
            for i in range(self.gpu_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                total_util += util.gpu
            return total_util / self.gpu_count
        except pynvml.NVMLError:
            return None

    def log_step_header(self, step_name: str):
        """
        Write a step header to the human-readable log.

        Args:
            step_name: Name of the automate-metashape workflow step
        """
        with open(self.log_file, "a") as f:
            f.write(f"\n=== {step_name} ===\n")

    @contextmanager
    def monitor(self, api_call_name: str):
        """
        Context manager to monitor a Metashape API call.

        Args:
            api_call_name: Name of the Metashape API method (e.g., "matchPhotos")

        Usage:
            with monitor.monitor("matchPhotos"):
                chunk.matchPhotos(...)
        """
        # Sampling state
        cpu_samples = []
        gpu_samples = []
        stop_sampling = threading.Event()

        def sample_utilization():
            """Background thread to sample CPU/GPU utilization."""
            while not stop_sampling.is_set():
                # CPU utilization (system-wide)
                cpu_percent = psutil.cpu_percent(interval=None)
                cpu_samples.append(cpu_percent)

                # GPU utilization
                gpu_util = self._get_gpu_utilization()
                if gpu_util is not None:
                    gpu_samples.append(gpu_util)

                # Wait for next sample (1 second interval)
                stop_sampling.wait(timeout=1.0)

        # Start sampling thread
        sampler = threading.Thread(target=sample_utilization, daemon=True)
        start_time = time.time()
        sampler.start()

        try:
            yield
        finally:
            # Stop sampling and wait for thread
            stop_sampling.set()
            sampler.join(timeout=2.0)
            end_time = time.time()

            # Calculate metrics
            duration = end_time - start_time
            avg_cpu = sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0
            avg_gpu = sum(gpu_samples) / len(gpu_samples) if gpu_samples else None

            # Write to logs
            self._write_human_log(api_call_name, duration, avg_cpu, avg_gpu)
            self._write_yaml_log(api_call_name, duration, avg_cpu, avg_gpu)

    def _write_human_log(
        self, api_call: str, duration: float, cpu: float, gpu: float | None
    ):
        """Append entry to human-readable log."""
        duration_str = self._format_duration(duration)
        cpu_str = f"{cpu:.0f}%"
        gpu_str = f"{gpu:.0f}%" if gpu is not None else "N/A"

        with open(self.log_file, "a") as f:
            f.write(
                f"{api_call:<25} | {duration_str:>12} | {cpu_str:>8} | {gpu_str:>8}\n"
            )

    def _write_yaml_log(
        self, api_call: str, duration: float, cpu: float, gpu: float | None
    ):
        """Append entry to YAML log."""
        entry = {
            "api_call": api_call,
            "duration_seconds": round(duration, 1),
            "cpu_percent": round(cpu, 1),
        }

        if gpu is not None:
            entry["gpu_percent"] = round(gpu, 1)
        else:
            entry["gpu_percent"] = "N/A"

        # Append to YAML file
        with open(self.yaml_log_path, "a") as f:
            yaml.dump([entry], f, default_flow_style=False)
            f.write("\n")

    def close(self):
        """Clean up resources."""
        if self.gpu_available and PYNVML_AVAILABLE:
            try:
                pynvml.nvmlShutdown()
            except pynvml.NVMLError:
                pass

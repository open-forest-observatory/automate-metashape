"""
Benchmark monitoring for Metashape API calls.

Provides a context manager that wraps API calls and logs:
- Duration
- Average CPU utilization
- Average GPU utilization

Integrates with the existing log file and adds a machine-readable YAML format.
"""

import os
import platform
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

    def __init__(self, log_file: str, yaml_log_path: str, get_system_info_fn=None):
        """
        Initialize the benchmark monitor.

        Args:
            log_file: Path to existing human-readable log file (appends to it)
            yaml_log_path: Path for machine-readable YAML metrics file
            get_system_info_fn: Callable that returns current system info dict.
                                Called fresh for each API call to handle different nodes per step.
        """
        self.log_file = log_file
        self.yaml_log_path = yaml_log_path
        self.get_system_info_fn = get_system_info_fn
        self.current_step = ""  # Store current step name

        # GPU initialization for monitoring
        self.gpu_available = False
        self.gpu_count = 0
        if PYNVML_AVAILABLE:
            try:
                pynvml.nvmlInit()
                self.gpu_count = pynvml.nvmlDeviceGetCount()
                self.gpu_available = self.gpu_count > 0
            except pynvml.NVMLError:
                pass

        # Write YAML header - system info will be per-call now
        with open(self.yaml_log_path, "w") as f:
            f.write("api_calls:\n")

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
        Store the current step name for inclusion in log entries.

        Args:
            step_name: Name of the automate-metashape workflow step
        """
        self.current_step = step_name

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

            # Calculate and round metrics to 1 decimal place
            duration = round(end_time - start_time, 1)
            cpu_percent = round(sum(cpu_samples) / len(cpu_samples), 1) if cpu_samples else 0.0
            gpu_percent = round(sum(gpu_samples) / len(gpu_samples), 1) if gpu_samples else None

            # Get fresh system info for this API call (may be different node per step)
            system_info = self.get_system_info_fn() if self.get_system_info_fn else {}

            # Write to logs
            self._write_human_log(api_call_name, duration, cpu_percent, gpu_percent, system_info)
            self._write_yaml_log(api_call_name, duration, cpu_percent, gpu_percent, system_info)

    def _write_human_log(
        self, api_call: str, duration: float, cpu_percent: float, gpu_percent: float | None, system_info: dict
    ):
        """Append entry to human-readable log."""
        duration_str = self._format_duration(duration)
        cpu_str = f"{cpu_percent:>3.0f}"
        gpu_str = f"{gpu_percent:>3.0f}" if gpu_percent is not None else "N/A"

        # Extract node info - use "N/A" for missing values in TXT log
        cpu_cores_available = system_info.get("cpu_cores_available", "N/A")
        gpu_count = system_info.get("gpu_count", "N/A")
        gpu_model = system_info.get("gpu_model") or "N/A"
        node_name = system_info.get("node", "N/A")

        with open(self.log_file, "a") as f:
            f.write(
                f"{self.current_step:<18} | {api_call:<24} | {duration_str} | {cpu_str:>5} | {gpu_str:>5} | "
                f"{cpu_cores_available:>4} | {gpu_count:>4} | {gpu_model:<15} | {node_name:<15}\n"
            )

    def _write_yaml_log(
        self, api_call: str, duration: float, cpu_percent: float, gpu_percent: float | None, system_info: dict
    ):
        """Append entry to YAML log."""
        # Extract node info and convert None to 'null' for proper YAML formatting
        cpu_cores_available = system_info.get("cpu_cores_available")
        gpu_count = system_info.get("gpu_count")
        gpu_model = system_info.get("gpu_model")
        node_name = system_info.get("node")

        # Convert None to 'null' string for valid YAML
        cpu_cores_available = cpu_cores_available if cpu_cores_available is not None else 'null'
        gpu_count = gpu_count if gpu_count is not None else 'null'
        gpu_model = gpu_model if gpu_model is not None else 'null'
        node_name = node_name if node_name is not None else 'null'
        gpu_percent = gpu_percent if gpu_percent is not None else 'null'

        # Write as indented list item under api_calls
        with open(self.yaml_log_path, "a") as f:
            f.write(f"  - api_call: {api_call}\n")
            f.write(f"    duration_seconds: {duration}\n")
            f.write(f"    cpu_percent: {cpu_percent}\n")
            f.write(f"    gpu_percent: {gpu_percent}\n")
            f.write(f"    cpu_cores_available: {cpu_cores_available}\n")
            f.write(f"    gpu_count: {gpu_count}\n")
            f.write(f"    gpu_model: {gpu_model}\n")
            f.write(f"    node_name: {node_name}\n")

    def close(self):
        """Clean up resources."""
        if self.gpu_available and PYNVML_AVAILABLE:
            try:
                pynvml.nvmlShutdown()
            except pynvml.NVMLError:
                pass

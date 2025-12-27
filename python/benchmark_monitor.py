"""
Benchmark monitoring for Metashape API calls.

Provides a context manager that wraps API calls and logs:
- Duration
- Average CPU utilization
- Average GPU utilization
- Peak memory usage (process, container, and system level)

Integrates with the existing log file and adds a machine-readable YAML format.
"""

import os
import platform
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import psutil
import yaml

# Try to import pynvml for GPU monitoring
try:
    import pynvml

    PYNVML_AVAILABLE = True
except ImportError:
    PYNVML_AVAILABLE = False


# cgroups v2 paths for container memory limits
CGROUP_V2_MEMORY_MAX = Path("/sys/fs/cgroup/memory.max")
CGROUP_V2_MEMORY_CURRENT = Path("/sys/fs/cgroup/memory.current")


def _is_in_cgroup_v2() -> bool:
    """Check if running inside a cgroups v2 container with memory limits."""
    return CGROUP_V2_MEMORY_MAX.exists() and CGROUP_V2_MEMORY_CURRENT.exists()


def _read_cgroup_memory_limit() -> int | None:
    """
    Read container memory limit from cgroups v2.

    Returns:
        Memory limit in bytes, or None if unlimited/unavailable.
    """
    try:
        content = CGROUP_V2_MEMORY_MAX.read_text().strip()
        if content == "max":
            # No limit set, return None to indicate unlimited
            return None
        return int(content)
    except (OSError, ValueError):
        return None


def _read_cgroup_memory_current() -> int | None:
    """
    Read current container memory usage from cgroups v2.

    Returns:
        Current memory usage in bytes, or None if unavailable.
    """
    try:
        return int(CGROUP_V2_MEMORY_CURRENT.read_text().strip())
    except (OSError, ValueError):
        return None


def _bytes_to_gb(bytes_val: int | None) -> float | None:
    """Convert bytes to gigabytes, handling None."""
    if bytes_val is None:
        return None
    return bytes_val / (1024 * 1024 * 1024)


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

        # Get current process for CPU monitoring (including all children)
        self.process = psutil.Process()

        # Write YAML header - system info will be per-call now
        with open(self.yaml_log_path, "w") as f:
            f.write("api_calls:\n")

    def _format_duration(self, seconds: float) -> str:
        """Format duration as HH:MM:SS."""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _get_process_cpu_cores(self) -> float:
        """
        Get CPU usage in cores for this process and all children.

        Returns:
            Number of CPU cores being used (e.g., 0.5, 1.2, 4.0)
        """
        try:
            # Get all processes (main process + children recursively)
            processes = [self.process] + self.process.children(recursive=True)

            # Sum CPU percent across all processes
            total_cpu_percent = 0.0
            for proc in processes:
                try:
                    # cpu_percent() returns percentage of ONE CPU core (0-100)
                    # If using 2 full cores, this returns 200
                    total_cpu_percent += proc.cpu_percent(interval=None)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    # Process may have terminated, skip it
                    continue

            # Convert to number of cores (200% = 2.0 cores)
            return total_cpu_percent / 100.0
        except Exception:
            return 0.0

    def _get_process_memory_bytes(self) -> int:
        """
        Get RSS memory usage in bytes for this process and all children.

        Returns:
            Total RSS memory in bytes across main process and all subprocesses.
        """
        try:
            processes = [self.process] + self.process.children(recursive=True)
            total_rss = 0
            for proc in processes:
                try:
                    total_rss += proc.memory_info().rss
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            return total_rss
        except Exception:
            return 0

    def _get_memory_metrics(self) -> dict:
        """
        Get comprehensive memory metrics for process, container, and system.

        Returns:
            Dictionary with memory metrics in GB:
            - proc_mem_gb: Process + children RSS
            - container_limit_gb: Container memory limit (or system total if no container)
            - container_used_gb: Container memory used (or system used if no container)
            - container_avail_gb: Container memory available (limit - used)
            - sys_total_gb: System total memory (node level)
            - sys_used_gb: System used memory (node level)
            - sys_avail_gb: System available memory (node level)
        """
        # Process memory (always from psutil)
        proc_mem_bytes = self._get_process_memory_bytes()

        # System memory (node level, always from psutil)
        sys_mem = psutil.virtual_memory()
        sys_total = sys_mem.total
        sys_used = sys_mem.used
        sys_avail = sys_mem.available

        # Container memory (from cgroups v2 if available, else fall back to system)
        if _is_in_cgroup_v2():
            container_limit = _read_cgroup_memory_limit()
            container_used = _read_cgroup_memory_current()

            # If limit is None (unlimited), fall back to system total
            if container_limit is None:
                container_limit = sys_total

            # If current read failed, fall back to system used
            if container_used is None:
                container_used = sys_used

            container_avail = container_limit - container_used
        else:
            # Not in a container, use system values
            container_limit = sys_total
            container_used = sys_used
            container_avail = sys_avail

        return {
            "proc_mem_gb": _bytes_to_gb(proc_mem_bytes),
            "container_limit_gb": _bytes_to_gb(container_limit),
            "container_used_gb": _bytes_to_gb(container_used),
            "container_avail_gb": _bytes_to_gb(container_avail),
            "sys_total_gb": _bytes_to_gb(sys_total),
            "sys_used_gb": _bytes_to_gb(sys_used),
            "sys_avail_gb": _bytes_to_gb(sys_avail),
        }

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

    def set_step_name(self, step_name: str):
        """
        Set the current step name to be included in subsequent log entries.

        This sets the step context for all API calls monitored within this step.
        The step name appears in both human-readable and YAML log outputs.

        Args:
            step_name: Human-readable name of the workflow step (e.g., "Match Photos")
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
        process_cpu_samples = []
        memory_samples = []  # List of memory metric dicts
        stop_sampling = threading.Event()

        def sample_utilization():
            """Background thread to sample CPU/GPU/memory utilization."""
            while not stop_sampling.is_set():
                # CPU utilization (system-wide)
                cpu_percent = psutil.cpu_percent(interval=None)
                cpu_samples.append(cpu_percent)

                # GPU utilization
                gpu_util = self._get_gpu_utilization()
                if gpu_util is not None:
                    gpu_samples.append(gpu_util)

                # Process CPU usage (in cores)
                process_cpu = self._get_process_cpu_cores()
                process_cpu_samples.append(process_cpu)

                # Memory metrics (for peak tracking)
                mem_metrics = self._get_memory_metrics()
                memory_samples.append(mem_metrics)

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
            cpu_percent = (
                round(sum(cpu_samples) / len(cpu_samples), 1) if cpu_samples else 0.0
            )
            gpu_percent = (
                round(sum(gpu_samples) / len(gpu_samples), 1) if gpu_samples else None
            )
            process_cpu_cores = (
                round(sum(process_cpu_samples) / len(process_cpu_samples), 1)
                if process_cpu_samples
                else 0.0
            )

            # Calculate peak memory metrics
            if memory_samples:
                peak_memory = {
                    "proc_mem_peak_gb": round(
                        max(s["proc_mem_gb"] for s in memory_samples), 1
                    ),
                    "container_limit_gb": round(
                        memory_samples[-1]["container_limit_gb"], 1
                    ),
                    "container_used_peak_gb": round(
                        max(s["container_used_gb"] for s in memory_samples), 1
                    ),
                    "container_avail_min_gb": round(
                        min(s["container_avail_gb"] for s in memory_samples), 1
                    ),
                    "sys_total_gb": round(memory_samples[-1]["sys_total_gb"], 1),
                    "sys_used_peak_gb": round(
                        max(s["sys_used_gb"] for s in memory_samples), 1
                    ),
                    "sys_avail_min_gb": round(
                        min(s["sys_avail_gb"] for s in memory_samples), 1
                    ),
                }
            else:
                # No samples, get current snapshot
                current_mem = self._get_memory_metrics()
                peak_memory = {
                    "proc_mem_peak_gb": round(current_mem["proc_mem_gb"], 1),
                    "container_limit_gb": round(current_mem["container_limit_gb"], 1),
                    "container_used_peak_gb": round(current_mem["container_used_gb"], 1),
                    "container_avail_min_gb": round(current_mem["container_avail_gb"], 1),
                    "sys_total_gb": round(current_mem["sys_total_gb"], 1),
                    "sys_used_peak_gb": round(current_mem["sys_used_gb"], 1),
                    "sys_avail_min_gb": round(current_mem["sys_avail_gb"], 1),
                }

            # Get fresh system info for this API call (may be different node per step)
            system_info = self.get_system_info_fn() if self.get_system_info_fn else {}

            # Write to logs
            self._write_human_log(
                api_call_name,
                duration,
                cpu_percent,
                gpu_percent,
                process_cpu_cores,
                peak_memory,
                system_info,
            )
            self._write_yaml_log(
                api_call_name,
                duration,
                cpu_percent,
                gpu_percent,
                process_cpu_cores,
                peak_memory,
                system_info,
            )

    def _write_human_log(
        self,
        api_call: str,
        duration: float,
        cpu_percent: float,
        gpu_percent: float | None,
        process_cpu_cores: float,
        peak_memory: dict,
        system_info: dict,
    ):
        """Append entry to human-readable log."""
        duration_str = self._format_duration(duration)
        cpu_str = f"{cpu_percent:>3.0f}"
        gpu_str = f"{gpu_percent:>3.0f}" if gpu_percent is not None else "N/A"
        process_cpu_str = f"{process_cpu_cores:>4.1f}"

        # Extract node info - use "N/A" for missing values in TXT log
        cpu_cores_available = system_info.get("cpu_cores_available", "N/A")
        gpu_count = system_info.get("gpu_count", "N/A")
        gpu_model = system_info.get("gpu_model") or "N/A"
        node_name = system_info.get("node", "N/A")

        # Format memory values (in GB, with 1 decimal place)
        proc_mem = f"{peak_memory['proc_mem_peak_gb']:>6.1f}"
        ctr_limit = f"{peak_memory['container_limit_gb']:>6.1f}"
        ctr_used = f"{peak_memory['container_used_peak_gb']:>6.1f}"
        ctr_avail = f"{peak_memory['container_avail_min_gb']:>6.1f}"
        sys_total = f"{peak_memory['sys_total_gb']:>6.1f}"
        sys_used = f"{peak_memory['sys_used_peak_gb']:>6.1f}"
        sys_avail = f"{peak_memory['sys_avail_min_gb']:>6.1f}"

        with open(self.log_file, "a") as f:
            f.write(
                f"{self.current_step:<23} | {api_call:<35} | {duration_str} | "
                f"{cpu_str:>5} | {gpu_str:>5} | {process_cpu_str:>9} | "
                f"{proc_mem} | {ctr_limit} | {ctr_used} | {ctr_avail} | "
                f"{sys_total} | {sys_used} | {sys_avail} | "
                f"{cpu_cores_available:>4} | {gpu_count:>4} | {gpu_model:<15} | {node_name:<15}\n"
            )

    def _write_yaml_log(
        self,
        api_call: str,
        duration: float,
        cpu_percent: float,
        gpu_percent: float | None,
        process_cpu_cores: float,
        peak_memory: dict,
        system_info: dict,
    ):
        """Append entry to YAML log."""
        # Extract node info and convert None to 'null' for proper YAML formatting
        cpu_cores_available = system_info.get("cpu_cores_available")
        gpu_count = system_info.get("gpu_count")
        gpu_model = system_info.get("gpu_model")
        node_name = system_info.get("node")

        # Convert None to 'null' string for valid YAML
        cpu_cores_available = (
            cpu_cores_available if cpu_cores_available is not None else "null"
        )
        gpu_count = gpu_count if gpu_count is not None else "null"
        gpu_model = gpu_model if gpu_model is not None else "null"
        node_name = node_name if node_name is not None else "null"
        gpu_percent = gpu_percent if gpu_percent is not None else "null"

        # Write as indented list item under api_calls
        with open(self.yaml_log_path, "a") as f:
            f.write(f"  - api_call: {api_call}\n")
            f.write(f"    duration_seconds: {duration}\n")
            f.write(f"    cpu_percent: {cpu_percent}\n")
            f.write(f"    gpu_percent: {gpu_percent}\n")
            f.write(f"    cpu_cores_used: {process_cpu_cores}\n")
            f.write(f"    cpu_cores_available: {cpu_cores_available}\n")
            # Memory metrics (all in GB)
            f.write(f"    proc_mem_peak_gb: {peak_memory['proc_mem_peak_gb']}\n")
            f.write(f"    container_limit_gb: {peak_memory['container_limit_gb']}\n")
            f.write(
                f"    container_used_peak_gb: {peak_memory['container_used_peak_gb']}\n"
            )
            f.write(
                f"    container_avail_min_gb: {peak_memory['container_avail_min_gb']}\n"
            )
            f.write(f"    sys_total_gb: {peak_memory['sys_total_gb']}\n")
            f.write(f"    sys_used_peak_gb: {peak_memory['sys_used_peak_gb']}\n")
            f.write(f"    sys_avail_min_gb: {peak_memory['sys_avail_min_gb']}\n")
            # GPU and node info
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

#!/usr/bin/env python3
"""
Wrapper script that runs metashape_workflow.py with license retry logic.

Monitors the first N lines of output for "license not found" errors.
If detected, terminates the subprocess immediately and retries after a delay.
This prevents wasting hours of compute on jobs that will fail at save time.

Environment variables:
  LICENSE_MAX_RETRIES: Maximum retry attempts (0 = no retries/fail immediately, -1 = unlimited, >0 = that many retries). Default: 0
  LICENSE_RETRY_INTERVAL: Seconds between retries (default: 300)
  LICENSE_CHECK_LINES: Number of lines to monitor for license errors (default: 20)
"""

import collections
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# Global reference to the child process for signal handling
_child_process = None


class OutputMonitor:
    """
    Monitor subprocess output with heartbeat, selective pass-through, buffering, and full logging.

    Features:
    - Circular buffer: Keeps last N lines in memory for error context dump
    - Full log file: Writes every line to disk (on shared volume, no timestamps added)
    - Heartbeat: Periodic status messages proving process liveness (with recent line sample)
    - Selective pass-through: Only prints important lines to console (progress, license, monitor messages)
    - Full output mode: When LOG_HEARTBEAT_INTERVAL=0, prints all lines like original behavior
    """

    def __init__(self, log_file_path=None):
        """
        Initialize the output monitor.

        Args:
            log_file_path: Path to full log file (optional). If None, no file logging.
        """
        # Configuration from environment variables
        self.buffer_size = int(os.environ.get("LOG_BUFFER_SIZE", 100))
        self.heartbeat_interval = int(os.environ.get("LOG_HEARTBEAT_INTERVAL", 60))

        # If heartbeat interval is 0, enable full output mode (print all lines)
        self.full_output_mode = self.heartbeat_interval == 0

        # State
        self.buffer = collections.deque(maxlen=self.buffer_size)
        self.line_count = 0
        self.start_time = time.time()
        self.last_heartbeat = self.start_time
        self.last_content_line = ""  # Track most recent Metashape output line
        self.last_progress = ""  # Track most recent progress update (e.g., "buildDepthMaps: 45%")
        self.current_operation = ""  # Track current operation name for start/complete detection
        self.log_file = None

        # Important line prefixes to always pass through to console (in sparse mode)
        self.important_prefixes = (
            "[automate-metashape-progress]",
            "[automate-metashape-license-wrapper]",
            "[automate-metashape-monitor]",
            "[automate-metashape-heartbeat]",
        )

        # Open full log file if path provided
        if log_file_path:
            log_dir = os.path.dirname(log_file_path)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            self.log_file = open(log_file_path, "w", buffering=1)  # Line buffered
            print(f"[automate-metashape-monitor] Full log: {log_file_path}")

        if self.full_output_mode:
            print("[automate-metashape-monitor] Full output mode enabled (LOG_HEARTBEAT_INTERVAL=0)")

    def process_line(self, line):
        """
        Process a single line of subprocess output.

        - Adds to circular buffer
        - Writes to full log file (as-is, no timestamps added)
        - In full mode: prints every line to console
        - In sparse mode: only prints important lines + heartbeat with recent line sample

        Args:
            line: Line of output from subprocess (includes newline)

        Returns:
            str: The line unchanged (for compatibility with license checking)
        """
        self.line_count += 1
        self.buffer.append(line)

        # Write every line to full log file (no timestamp overhead)
        if self.log_file:
            self.log_file.write(line)

        if self.full_output_mode:
            # Full output mode: print every line (original behavior)
            print(line, end="")
        else:
            # Sparse mode: selective pass-through with heartbeat

            # Track last interesting line (not our own system messages) for heartbeat display
            stripped = line.strip()
            if stripped.startswith("[automate-metashape-progress]"):
                # Store latest progress for inclusion in heartbeat; don't print separately
                # Format: "[automate-metashape-progress] operationName: XX%"
                self.last_progress = stripped.replace("[automate-metashape-progress] ", "", 1)
                # Parse operation name (everything before ": XX%")
                op_name = self.last_progress.split(":")[0]
                # Detect operation transitions and print start/complete as heartbeat lines
                if op_name != self.current_operation:
                    self.current_operation = op_name
                    print(f"[automate-metashape-heartbeat] {time.strftime('%H:%M:%S')} | {op_name}: started")
                if "100%" in stripped:
                    print(f"[automate-metashape-heartbeat] {time.strftime('%H:%M:%S')} | {op_name}: completed")
            elif not any(line.startswith(prefix) for prefix in self.important_prefixes):
                self.last_content_line = stripped[:100]  # Truncate to 100 chars

            # Pass through important lines to console (except progress, which is folded into heartbeat)
            if any(line.startswith(prefix) for prefix in self.important_prefixes) and not line.startswith("[automate-metashape-progress]"):
                print(line, end="")

            # Check if it's time for a heartbeat
            now = time.time()
            if now - self.last_heartbeat >= self.heartbeat_interval:
                elapsed = now - self.start_time
                progress_display = (
                    f" | {self.last_progress}"
                    if self.last_progress
                    else ""
                )
                last_line_display = (
                    f" | last: {self.last_content_line}"
                    if self.last_content_line
                    else ""
                )
                print(
                    f"[automate-metashape-heartbeat] {time.strftime('%H:%M:%S')} | "
                    f"output lines: {self.line_count} | "
                    f"elapsed: {elapsed:.0f}s{progress_display}{last_line_display}"
                )
                self.last_heartbeat = now

        return line

    def dump_buffer(self):
        """Dump circular buffer contents to console (for error context)."""
        print(f"\n[automate-metashape-monitor] === Last {len(self.buffer)} lines before error ===")
        for line in self.buffer:
            print(line, end="")
        print("[automate-metashape-monitor] === End error context ===\n")

    def print_summary(self, exit_code):
        """Print final summary of processing."""
        elapsed = time.time() - self.start_time
        status = "SUCCESS" if exit_code == 0 else f"FAILED (exit code {exit_code})"
        print(
            f"[automate-metashape-monitor] {status} | "
            f"total output lines: {self.line_count} | "
            f"elapsed: {elapsed:.0f}s"
        )
        if self.log_file:
            print(f"[automate-metashape-monitor] Full metashape output log saved to: {self.log_file.name}")

    def close(self):
        """Clean up resources."""
        if self.log_file:
            self.log_file.close()

    def reset(self):
        """Reset state for a new retry attempt."""
        self.buffer.clear()
        self.line_count = 0
        self.start_time = time.time()
        self.last_heartbeat = self.start_time
        self.last_content_line = ""
        self.last_progress = ""
        self.current_operation = ""
        if self.log_file:
            # Truncate log file for new attempt
            self.log_file.seek(0)
            self.log_file.truncate()


def _compute_log_path(args):
    """
    Derive log file path from CLI arguments (--output-path and --step).

    Places log file on shared volume as a sibling to the output directory:
    /data/.../photogrammetry/metashape-<step>.log

    Args:
        args: Command-line arguments list (sys.argv[1:])

    Returns:
        str: Computed log file path, or fallback to /tmp if args not found
    """
    # Allow explicit override via environment variable
    override = os.environ.get("LOG_OUTPUT_DIR")

    output_path = None
    step = "unknown"
    i = 0
    while i < len(args):
        if args[i] == "--output-path" and i + 1 < len(args):
            output_path = args[i + 1]
        elif args[i] == "--step" and i + 1 < len(args):
            step = args[i + 1]
        i += 1

    if override:
        return os.path.join(override, f"metashape-{step}.log")
    elif output_path:
        # Place log as sibling to output dir
        parent = os.path.dirname(output_path.rstrip("/"))
        return os.path.join(parent, f"metashape-{step}.log")
    else:
        # Fallback to /tmp if we can't determine path from args
        return f"/tmp/metashape-{step}.log"


def _signal_handler(signum, frame):
    """Forward signals to the child process for graceful shutdown."""
    global _child_process
    if _child_process is not None and _child_process.poll() is None:
        sig_name = signal.Signals(signum).name
        print(f"[automate-metashape-license-wrapper] Received {sig_name}, forwarding to child process...")
        _child_process.send_signal(signum)


def run_with_license_retry():
    global _child_process

    max_retries = int(os.environ.get("LICENSE_MAX_RETRIES", 0))
    retry_interval = int(os.environ.get("LICENSE_RETRY_INTERVAL", 300))
    license_check_lines = int(os.environ.get("LICENSE_CHECK_LINES", 6))

    # Find metashape_workflow.py relative to this script
    script_dir = Path(__file__).parent
    workflow_script = script_dir / "metashape_workflow.py"

    # Pass through all command-line arguments
    cmd = [sys.executable, str(workflow_script)] + sys.argv[1:]

    # Compute log file path from arguments
    log_file_path = _compute_log_path(sys.argv[1:])

    # Create output monitor (persists across retry attempts)
    monitor = OutputMonitor(log_file_path)

    # Set up signal handlers to forward termination signals to child
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    attempt = 0
    while True:
        attempt += 1
        monitor.reset()
        print(f"[automate-metashape-license-wrapper] Starting Metashape workflow (attempt {attempt})...")

        _child_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        license_error = False
        line_count = 0

        for line in _child_process.stdout:
            # License check phase: first N lines are always printed directly
            # (needed for license error detection to work)
            if line_count < license_check_lines:
                print(line, end="")

                # Also track in monitor (buffer + full log, but skip duplicate console print)
                monitor.buffer.append(line)
                monitor.line_count += 1
                if monitor.log_file:
                    monitor.log_file.write(line)

                # Check for license error
                line_lower = line.lower()
                if (
                    "license not found" in line_lower
                    or "no license found" in line_lower
                ):
                    license_error = True
                    _child_process.terminate()
                    _child_process.wait()
                    break

                line_count += 1
                if line_count >= license_check_lines:
                    print(
                        "[automate-metashape-license-wrapper] License check passed, proceeding with workflow..."
                    )
            else:
                # Post-license-check: use monitor for selective output
                monitor.process_line(line)

        _child_process.wait()

        if license_error:
            # max_retries: 0 = no retries (fail immediately), -1 = unlimited, >0 = that many retries
            if max_retries == 0:
                print(
                    "[automate-metashape-license-wrapper] No license available and retries disabled (LICENSE_MAX_RETRIES=0)"
                )
                monitor.close()
                sys.exit(1)
            if max_retries > 0 and attempt > max_retries:
                print(f"[automate-metashape-license-wrapper] Max retries ({max_retries}) exceeded")
                monitor.close()
                sys.exit(1)
            print(
                f"[automate-metashape-license-wrapper] No license available. Waiting {retry_interval}s before retry..."
            )
            time.sleep(retry_interval)
            continue

        # Process completed (not a license error)
        if _child_process.returncode != 0:
            # Non-zero exit: dump error context buffer
            monitor.dump_buffer()

        monitor.print_summary(_child_process.returncode)
        monitor.close()
        sys.exit(_child_process.returncode)


if __name__ == "__main__":
    run_with_license_retry()

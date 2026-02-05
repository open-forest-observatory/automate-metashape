#!/usr/bin/env python3
"""
Wrapper script that runs metashape_workflow.py with license retry logic.

Monitors the first N lines of output for "license not found" errors.
If detected, terminates the subprocess immediately and retries after a delay.
This prevents wasting hours of compute on jobs that will fail at save time.

Environment variables:
  LICENSE_MAX_RETRIES: Maximum retry attempts (0 = unlimited, default: 0)
  LICENSE_RETRY_INTERVAL: Seconds between retries (default: 300)
  LICENSE_CHECK_LINES: Number of lines to monitor for license errors (default: 20)
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# Global reference to the child process for signal handling
_child_process = None


def _signal_handler(signum, frame):
    """Forward signals to the child process for graceful shutdown."""
    global _child_process
    if _child_process is not None and _child_process.poll() is None:
        sig_name = signal.Signals(signum).name
        print(f"[license-wrapper] Received {sig_name}, forwarding to child process...")
        _child_process.send_signal(signum)


def run_with_license_retry():
    global _child_process

    max_retries = int(os.environ.get("LICENSE_MAX_RETRIES", 0))
    retry_interval = int(os.environ.get("LICENSE_RETRY_INTERVAL", 300))
    license_check_lines = int(os.environ.get("LICENSE_CHECK_LINES", 20))

    # Find metashape_workflow.py relative to this script
    script_dir = Path(__file__).parent
    workflow_script = script_dir / "metashape_workflow.py"

    # Pass through all command-line arguments
    cmd = [sys.executable, str(workflow_script)] + sys.argv[1:]

    # Set up signal handlers to forward termination signals to child
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    attempt = 0
    while True:
        attempt += 1
        print(f"[license-wrapper] Starting Metashape workflow (attempt {attempt})...")

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
            print(line, end="")

            # Only check first N lines for license error
            if line_count < license_check_lines:
                line_lower = line.lower()
                if "license not found" in line_lower or "no license found" in line_lower:
                    license_error = True
                    _child_process.terminate()
                    _child_process.wait()
                    break
                line_count += 1
                if line_count >= license_check_lines:
                    print(
                        "[license-wrapper] License check passed, proceeding with workflow..."
                    )

        _child_process.wait()

        if license_error:
            if max_retries > 0 and attempt >= max_retries:
                print(f"[license-wrapper] Max retries ({max_retries}) exceeded")
                sys.exit(1)
            print(
                f"[license-wrapper] No license available. Waiting {retry_interval}s before retry..."
            )
            time.sleep(retry_interval)
            continue

        # Not a license error - exit with subprocess exit code
        sys.exit(_child_process.returncode)


if __name__ == "__main__":
    run_with_license_retry()

"""Process watchdog daemon with 3-second auto-restart and crash-loop protection."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from collections import deque
from pathlib import Path


def run_watchdog(
    demo: bool = False,
    duration: int = 0,
    max_restarts_per_min: int = 5,
    logs_dir: Path = Path("logs"),
) -> int:
    logs_dir.mkdir(parents=True, exist_ok=True)
    stop_signal = logs_dir / "stop.signal"
    restart_times: deque[float] = deque()

    cmd = [sys.executable, "rtsp_multichannel_monitor.py"]
    if demo:
        cmd.append("--demo")
    if duration > 0:
        cmd.extend(["--duration", str(duration)])

    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

    while True:
        if stop_signal.exists():
            print("[WATCHDOG] Stop signal found. Exiting.")
            return 0

        proc = subprocess.Popen(cmd, creationflags=flags)
        (logs_dir / "monitor.pid").write_text(str(proc.pid), encoding="utf-8")
        exit_code = proc.wait()

        if stop_signal.exists() or (duration > 0 and exit_code == 0):
            return exit_code

        now = time.monotonic()
        restart_times.append(now)
        while restart_times and (now - restart_times[0]) > 60.0:
            restart_times.popleft()

        if len(restart_times) > max_restarts_per_min:
            print("[WATCHDOG] Crash-loop protection triggered (>5 restarts/min). Halting.")
            return 1

        print(f"[WATCHDOG] Monitor exited ({exit_code}). Restarting in 3s...")
        time.sleep(3)


def main() -> None:
    parser = argparse.ArgumentParser(description="Watchdog for RTSP monitor.")
    parser.add_argument("--demo", action="store_true", help="Run monitor in virtual camera demo mode")
    parser.add_argument("--duration", type=int, default=0, help="Run duration in seconds")
    args = parser.parse_args()
    raise SystemExit(run_watchdog(demo=args.demo, duration=args.duration))


if __name__ == "__main__":
    main()

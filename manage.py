"""Unified CLI entrypoint for rtsp-multichannel-qe-monitor."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from cleanup_logs import cleanup_old_files
from generate_daily_report import generate_report
from run_pipeline import build_camera_config
from web_dashboard import run_server


LOGS_DIR = Path("logs")
WATCHDOG_PID_FILE = LOGS_DIR / "watchdog.pid"
MONITOR_PID_FILE = LOGS_DIR / "monitor.pid"
STOP_SIGNAL_FILE = LOGS_DIR / "stop.signal"


def _is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong()
            if ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return exit_code.value == 259
            return True
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _has_live_cameras(cameras_path: Path) -> bool:
    if not cameras_path.exists():
        return False
    try:
        cams = json.loads(cameras_path.read_text(encoding="utf-8")).get("cameras", [])
        return any(
            c.get("rtsp_url") and not str(c.get("rtsp_url")).startswith("demo://")
            for c in cams
        )
    except Exception:
        return False


def cmd_start(discover: bool = False, demo: bool = False, duration: int = 0) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    if STOP_SIGNAL_FILE.exists():
        STOP_SIGNAL_FILE.unlink()

    cameras_path = Path("cameras.json")
    if discover:
        found = build_camera_config(cameras_path, demo=demo)
        if not demo and not found:
            print("[ERROR] 동일 네트워크에서 연결된 ONVIF/RTSP 카메라를 찾지 못했습니다. 카메라 연결을 확인하거나 가상 카메라 데모를 실행하세요.")
            raise SystemExit(1)

    if not demo and not _has_live_cameras(cameras_path):
        print("[ERROR] cameras.json에 등록된 실제 카메라(rtsp:// 또는 http://)가 없습니다. 주소를 등록하거나 '가상 카메라 데모 시작'을 이용해 주세요.")
        raise SystemExit(1)

    cmd = [sys.executable, "watchdog.py"]
    if demo:
        cmd.append("--demo")
    if duration > 0:
        cmd.extend(["--duration", str(duration)])

    if duration > 0:
        print(f"[MANAGE] Running {'demo ' if demo else ''}monitor for {duration}s...")
        proc = subprocess.run(cmd, check=False)
        raise SystemExit(proc.returncode)

    watchdog_log = (LOGS_DIR / "watchdog.log").open("a", encoding="utf-8")
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=watchdog_log,
            stderr=watchdog_log,
            creationflags=flags,
        )
    else:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=watchdog_log,
            stderr=watchdog_log,
            start_new_session=True,
        )
    WATCHDOG_PID_FILE.write_text(str(proc.pid), encoding="utf-8")
    time.sleep(0.5)
    print(f"[MANAGE] Started watchdog (PID={proc.pid}, mode={'demo' if demo else 'live'}).")


def cmd_status() -> None:
    for label, pid_file in [("Watchdog", WATCHDOG_PID_FILE), ("Monitor", MONITOR_PID_FILE)]:
        if not pid_file.exists():
            print(f"[STATUS] {label}: STOPPED (no PID file)")
            continue
        try:
            pid = int(pid_file.read_text(encoding="utf-8").strip())
        except ValueError:
            print(f"[STATUS] {label}: UNKNOWN (invalid PID)")
            continue
        state = "RUNNING" if _is_pid_running(pid) else "STOPPED"
        print(f"[STATUS] {label}: {state} (PID={pid})")


def cmd_stop() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    STOP_SIGNAL_FILE.write_text("stop", encoding="utf-8")

    for pid_file in (MONITOR_PID_FILE, WATCHDOG_PID_FILE):
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text(encoding="utf-8").strip())
                if _is_pid_running(pid):
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                    else:
                        os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
    time.sleep(0.5)
    print("[MANAGE] Stop signal sent to watchdog and monitor.")


def cmd_report(log_file: str | None = None, no_slack: bool = False) -> None:
    generate_report(log_file=log_file, send_slack=not no_slack)


def cmd_clean(days: int = 7, dry_run: bool = False) -> None:
    targets = cleanup_old_files(LOGS_DIR, days=days, dry_run=dry_run)
    tag = "[DRY-RUN]" if dry_run else "[CLEANED]"
    print(f"{tag} Files older than {days} day(s): {len(targets)}")
    for t in targets:
        print(f"  - {t}")


def main() -> None:
    parser = argparse.ArgumentParser(description="RTSP Multi-Channel QE Monitor CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Start watchdog & RTSP monitor")
    p_start.add_argument("--discover", action="store_true", help="Run ONVIF discovery first")
    p_start.add_argument("--demo", action="store_true", help="Run in virtual camera demo mode")
    p_start.add_argument("--duration", type=int, default=0, help="Run foreground demo for N seconds")

    sub.add_parser("status", help="Show running process status")
    sub.add_parser("stop", help="Gracefully stop watchdog & monitor")

    p_report = sub.add_parser("report", help="Generate daily summary Markdown report")
    p_report.add_argument("-f", "--file", help="Target log file path")
    p_report.add_argument("--no-slack", action="store_true", help="Skip Slack webhook posting")

    p_clean = sub.add_parser("clean", help="Clean up old logs, snapshots, and clips")
    p_clean.add_argument("--days", type=int, default=7, help="Retention days (default: 7)")
    p_clean.add_argument("--dry-run", action="store_true", help="Preview files without deleting")

    p_web = sub.add_parser("web", help="Launch real-time Web Dashboard")
    p_web.add_argument("--port", type=int, default=8890, help="Dashboard port (default: 8890)")
    p_web.add_argument("--no-browser", action="store_true", help="Do not auto-open browser")

    args = parser.parse_args()
    if args.command == "start":
        cmd_start(discover=args.discover, demo=args.demo, duration=args.duration)
    elif args.command == "status":
        cmd_status()
    elif args.command == "stop":
        cmd_stop()
    elif args.command == "report":
        cmd_report(log_file=args.file, no_slack=args.no_slack)
    elif args.command == "clean":
        cmd_clean(days=args.days, dry_run=args.dry_run)
    elif args.command == "web":
        run_server(port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()

"""Lightweight multi-channel RTSP stability monitor with Virtual Camera Demo Mode."""

from __future__ import annotations

import argparse
import json
import random
import signal
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, List

from disk_guard import check_disk_status
from network_bandwidth_monitor import NetworkBandwidthMonitor
from video_clip_recorder import save_incident_evidence


RUNNING = True


def _handle_signal(signum: int, frame: Any) -> None:  # noqa: ARG001
    global RUNNING
    RUNNING = False


def load_cameras(config_path: Path) -> List[Dict[str, str]]:
    if not config_path.exists():
        return []
    data = json.loads(config_path.read_text(encoding="utf-8"))
    return data.get("cameras", [])


def write_log(log_path: Path, message: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} {message}"
    print(line, flush=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_monitor(
    cameras_file: Path = Path("cameras.json"),
    logs_dir: Path = Path("logs"),
    demo: bool = False,
    duration: int = 0,
    interval: float = 1.0,
) -> int:
    global RUNNING
    RUNNING = True
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    logs_dir.mkdir(parents=True, exist_ok=True)
    stop_signal = logs_dir / "stop.signal"
    if stop_signal.exists():
        stop_signal.unlink()

    log_path = logs_dir / f"rtsp_multichannel_{datetime.now().strftime('%Y%m%d')}.log"
    cameras = load_cameras(cameras_file)

    if demo:
        if not cameras:
            cameras = [
                {"id": "CH01", "name": "Demo-Lobby", "rtsp_url": "demo://rtsp/192.168.10.101:554/stream1"},
                {"id": "CH02", "name": "Demo-Gate", "rtsp_url": "demo://rtsp/192.168.10.102:554/stream1"},
                {"id": "CH03", "name": "Demo-Parking", "rtsp_url": "demo://rtsp/192.168.10.103:554/stream1"},
                {"id": "CH04", "name": "Demo-Warehouse", "rtsp_url": "demo://rtsp/192.168.10.104:554/stream1"},
            ]
    else:
        live_cameras = [c for c in cameras if not str(c.get("rtsp_url", "")).startswith("demo://") and c.get("rtsp_url")]
        if not live_cameras:
            write_log(log_path, "[ERROR] No live camera URLs in cameras.json. Register rtsp:// or http:// URL, or run Demo mode.")
            return 1
        cameras = live_cameras

    net_mon = NetworkBandwidthMonitor()
    buffers: Dict[str, Deque[Any]] = {cam["id"]: deque(maxlen=50) for cam in cameras}
    caps: Dict[str, Any] = {}

    if not demo:
        try:
            import cv2  # type: ignore

            for cam in cameras:
                caps[cam["id"]] = cv2.VideoCapture(cam["rtsp_url"])
        except ImportError:
            write_log(log_path, "[ERROR] opencv-python is not installed. Run setup.bat or python -m pip install opencv-python.")
            return 1

    mode_label = "VIRTUAL-DEMO" if demo else "LIVE-RTSP"
    write_log(log_path, f"[START] Mode={mode_label} Channels={len(cameras)}")

    start_ts = time.monotonic()
    tick = 0

    try:
        while RUNNING:
            if stop_signal.exists():
                write_log(log_path, "[STOP] Stop signal detected. Graceful shutdown.")
                break
            if duration > 0 and (time.monotonic() - start_ts) >= duration:
                write_log(log_path, f"[STOP] Duration limit ({duration}s) reached.")
                break

            tick += 1
            frame_drops = 0

            if demo:
                if tick == 4:
                    cam = cameras[min(2, len(cameras) - 1)]
                    reason = "Stream freeze / frame drop burst (>15 frames)"
                    write_log(log_path, f"[INCIDENT] channel={cam['id']} reason={reason}")
                    ev = save_incident_evidence(cam["id"], reason, [], logs_dir, demo=True)
                    write_log(log_path, f"[EVIDENCE] channel={cam['id']} snapshot={ev['snapshot']} clip={ev['clip']}")
                    frame_drops += 18
                elif random.random() < 0.25:
                    frame_drops += random.randint(1, 3)
            else:
                import cv2  # type: ignore

                for cam in cameras:
                    cid = cam["id"]
                    cap = caps.get(cid)
                    if cap is None or not cap.isOpened():
                        frame_drops += 1
                        continue
                    grabbed = cap.grab()
                    if not grabbed:
                        frame_drops += 1
                        write_log(log_path, f"[INCIDENT] channel={cid} reason=RTSP grab failed / disconnect")
                        save_incident_evidence(cid, "RTSP disconnect", list(buffers[cid]), logs_dir, demo=False)
                        cap.release()
                        caps[cid] = cv2.VideoCapture(cam["rtsp_url"])
                        continue
                    if tick % 2 == 0:
                        ok, frm = cap.retrieve()
                        if ok and frm is not None:
                            small = cv2.resize(frm, (640, 360))
                            buffers[cid].append(small)

            net = net_mon.sample(demo=demo, active_channels=len(cameras))
            disk = check_disk_status(".", min_free_pct=10.0)
            write_log(
                log_path,
                f"[TELEMETRY] channels={len(cameras)} rx_mbps={net['rx_mbps']} "
                f"nic_drop={net['drop_delta']} frame_drops={frame_drops} "
                f"disk_free_pct={disk['free_pct']}",
            )
            time.sleep(interval)
    finally:
        for cap in caps.values():
            try:
                cap.release()
            except Exception:
                pass
        write_log(log_path, "[EXIT] RTSP monitor stopped cleanly.")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-channel RTSP stability monitor.")
    parser.add_argument("--demo", action="store_true", help="Run in virtual camera demo mode")
    parser.add_argument("--duration", type=int, default=0, help="Auto-stop after N seconds (0=forever)")
    parser.add_argument("--interval", type=float, default=1.0, help="Sampling interval in seconds")
    args = parser.parse_args()
    sys.exit(run_monitor(demo=args.demo, duration=args.duration, interval=args.interval))


if __name__ == "__main__":
    main()

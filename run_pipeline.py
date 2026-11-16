"""Pipeline: ONVIF discovery -> Credential match -> RTSP URI extract -> cameras.json update."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

from credential_matcher import match_camera_credentials
from discover_onvif import discover_onvif_devices
from extract_onvif_rtsp import extract_rtsp_uri


def build_camera_config(output_path: Path = Path("cameras.json"), demo: bool = False) -> List[Dict[str, str]]:
    devices = discover_onvif_devices(demo=demo)
    cameras: List[Dict[str, str]] = []

    for idx, dev in enumerate(devices, start=1):
        ip = dev["ip"]
        creds = match_camera_credentials(ip, demo=demo)
        if not creds:
            continue
        user, password = creds
        rtsp_url = extract_rtsp_uri(ip, user, password, demo=demo)
        cameras.append({
            "id": f"CH{idx:02d}",
            "name": dev.get("name", f"Cam-{ip}"),
            "ip": ip,
            "rtsp_url": rtsp_url,
        })

    if cameras or demo:
        output_path.write_text(
            json.dumps({"cameras": cameras}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"[PIPELINE] Updated {output_path} with {len(cameras)} camera(s).")
    else:
        print("[PIPELINE] No ONVIF cameras found; existing cameras.json preserved.")
    return cameras


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ONVIF discovery & update cameras.json.")
    parser.add_argument("--demo", action="store_true", help="Use virtual demo cameras")
    args = parser.parse_args()
    build_camera_config(demo=args.demo)


if __name__ == "__main__":
    main()

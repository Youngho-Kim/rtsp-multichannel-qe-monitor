"""Drop-in QE suite runner compatible with rtsp-multichannel-qe-monitor's cameras.json."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from camera_profile_validator import (
    CameraProfile,
    StreamProbeResult,
    probe_rtsp_ffprobe,
    validate_profile,
)
from qe_report_generator import (
    build_slack_summary,
    export_csv_report,
    export_html_report,
)
from stream_resilience_tester import make_simulated_probe, run_resilience_check


def load_cameras_flexibly(config_path: Path) -> list[CameraProfile]:
    """Load either cameras.json (existing monitor format) or camera_profiles.json."""
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    items = raw.get("cameras", raw) if isinstance(raw, dict) else raw
    profiles: list[CameraProfile] = []
    for idx, item in enumerate(items, start=1):
        rtsp_url = item.get("rtsp_url") or item.get("url") or ""
        vendor = item.get("vendor") or item.get("name") or f"Camera-{idx}"
        model = item.get("model") or item.get("channel") or f"CH{idx}"
        profiles.append(
            CameraProfile(
                vendor=str(vendor),
                model=str(model),
                rtsp_url=str(rtsp_url),
                expected_codec=str(item.get("expected_codec", "h264")),
                expected_width=int(item.get("expected_width", 1920)),
                expected_height=int(item.get("expected_height", 1080)),
                expected_fps=float(item.get("expected_fps", 30.0)),
                fps_tolerance=float(item.get("fps_tolerance", 3.0)),
                max_gop_seconds=float(item.get("max_gop_seconds", 2.0)),
            )
        )
    return profiles


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RTSP QE profile & resilience suite")
    parser.add_argument("--config", default="camera_profiles.json", help="Path to cameras.json or camera_profiles.json")
    parser.add_argument("--report-dir", default="reports", help="Directory for HTML/CSV reports")
    parser.add_argument("--checks", type=int, default=20, help="Resilience checks per channel")
    parser.add_argument("--demo", action="store_true", help="Run with simulated camera probes")
    args = parser.parse_args()

    profiles = load_cameras_flexibly(Path(args.config))
    validations = []
    resilience = []

    for i, prof in enumerate(profiles):
        if args.demo:
            probe_res = StreamProbeResult(
                codec=prof.expected_codec,
                width=prof.expected_width,
                height=prof.expected_height,
                fps=prof.expected_fps if i % 2 == 0 else round(prof.expected_fps - 4.0, 1),
                gop_seconds=1.5,
                reachable=True,
            )
            probe_fn = make_simulated_probe(0.15, 0.85, seed=100 + i)
            retry_delay = 0.0
        else:
            probe_res = probe_rtsp_ffprobe(prof.rtsp_url)
            probe_fn = lambda url=prof.rtsp_url: probe_rtsp_ffprobe(url, timeout_sec=4).reachable
            retry_delay = 1.0

        validations.append(validate_profile(prof, probe_res))
        resilience.append(
            run_resilience_check(
                channel_id=f"ch{i + 1}",
                vendor=prof.vendor,
                probe_fn=probe_fn,
                total_checks=args.checks,
                retry_delay_sec=retry_delay,
            )
        )

    out_dir = Path(args.report_dir)
    html_path = export_html_report(validations, resilience, out_dir / "qe_report.html")
    csv_path = export_csv_report(validations, resilience, out_dir / "qe_report.csv")
    print(f"HTML report: {html_path}")
    print(f"CSV report:  {csv_path}")
    print(build_slack_summary(validations, resilience))


if __name__ == "__main__":
    main()
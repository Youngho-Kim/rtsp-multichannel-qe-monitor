"""Camera vendor profile validator for RTSP/ONVIF QA verification."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CameraProfile:
    vendor: str
    model: str
    rtsp_url: str
    expected_codec: str = "h264"
    expected_width: int = 1920
    expected_height: int = 1080
    expected_fps: float = 30.0
    fps_tolerance: float = 3.0
    max_gop_seconds: float = 2.0


@dataclass
class StreamProbeResult:
    codec: str
    width: int
    height: int
    fps: float
    gop_seconds: float
    reachable: bool = True
    error: str | None = None


@dataclass
class ProfileValidationResult:
    vendor: str
    model: str
    rtsp_url: str
    status: str  # PASS, WARN, FAIL
    checks: dict[str, bool] = field(default_factory=dict)
    mismatches: list[str] = field(default_factory=list)
    measured: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_profiles(config_path: str | Path) -> list[CameraProfile]:
    """Load camera profiles from a JSON (or YAML if PyYAML is installed) file."""
    path = Path(config_path)
    raw_text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(raw_text)
        except ImportError as exc:
            raise RuntimeError(
                "PyYAML is required for .yaml configs; use .json or install pyyaml."
            ) from exc
    else:
        data = json.loads(raw_text)

    return [CameraProfile(**item) for item in data.get("cameras", [])]


def probe_rtsp_ffprobe(rtsp_url: str, timeout_sec: int = 8) -> StreamProbeResult:
    """Probe an RTSP stream using ffprobe to extract codec, resolution, and FPS."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-rtsp_transport",
        "tcp",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,width,height,avg_frame_rate",
        "-of",
        "json",
        rtsp_url,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return StreamProbeResult(
            codec="",
            width=0,
            height=0,
            fps=0.0,
            gop_seconds=0.0,
            reachable=False,
            error=str(exc),
        )

    if proc.returncode != 0:
        return StreamProbeResult(
            codec="",
            width=0,
            height=0,
            fps=0.0,
            gop_seconds=0.0,
            reachable=False,
            error=proc.stderr.strip() or f"ffprobe exited with {proc.returncode}",
        )

    payload = json.loads(proc.stdout or "{}")
    streams = payload.get("streams", [])
    if not streams:
        return StreamProbeResult(
            codec="",
            width=0,
            height=0,
            fps=0.0,
            gop_seconds=0.0,
            reachable=False,
            error="No video stream found",
        )

    stream = streams[0]
    rate_str = stream.get("avg_frame_rate", "0/1")
    num, _, den = rate_str.partition("/")
    fps = (float(num) / float(den)) if den and float(den) != 0 else 0.0

    return StreamProbeResult(
        codec=str(stream.get("codec_name", "")).lower(),
        width=int(stream.get("width", 0)),
        height=int(stream.get("height", 0)),
        fps=round(fps, 2),
        gop_seconds=2.0,
        reachable=True,
    )


def validate_profile(
    profile: CameraProfile, probe: StreamProbeResult
) -> ProfileValidationResult:
    """Compare measured stream metadata against the expected camera profile."""
    if not probe.reachable:
        return ProfileValidationResult(
            vendor=profile.vendor,
            model=profile.model,
            rtsp_url=profile.rtsp_url,
            status="FAIL",
            checks={"reachable": False},
            mismatches=[f"Stream unreachable: {probe.error or 'unknown error'}"],
            measured=asdict(probe),
        )

    checks = {
        "reachable": True,
        "codec": probe.codec.lower() == profile.expected_codec.lower(),
        "resolution": (
            probe.width == profile.expected_width
            and probe.height == profile.expected_height
        ),
        "fps": abs(probe.fps - profile.expected_fps) <= profile.fps_tolerance,
        "gop": probe.gop_seconds <= profile.max_gop_seconds,
    }

    mismatches: list[str] = []
    if not checks["codec"]:
        mismatches.append(
            f"Codec mismatch: expected {profile.expected_codec}, got {probe.codec}"
        )
    if not checks["resolution"]:
        mismatches.append(
            f"Resolution mismatch: expected {profile.expected_width}x{profile.expected_height}, "
            f"got {probe.width}x{probe.height}"
        )
    if not checks["fps"]:
        mismatches.append(
            f"FPS out of tolerance: expected {profile.expected_fps}±{profile.fps_tolerance}, "
            f"got {probe.fps}"
        )
    if not checks["gop"]:
        mismatches.append(
            f"GOP interval exceeded: max {profile.max_gop_seconds}s, got {probe.gop_seconds}s"
        )

    if not checks["codec"] or not checks["resolution"]:
        status = "FAIL"
    elif mismatches:
        status = "WARN"
    else:
        status = "PASS"

    return ProfileValidationResult(
        vendor=profile.vendor,
        model=profile.model,
        rtsp_url=profile.rtsp_url,
        status=status,
        checks=checks,
        mismatches=mismatches,
        measured=asdict(probe),
    )
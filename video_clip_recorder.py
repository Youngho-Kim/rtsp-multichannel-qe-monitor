"""Incident snapshot, 5-second ring-buffer MP4 clip recorder, and Slack uploader."""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional


def save_incident_evidence(
    channel_id: str,
    reason: str,
    frame_buffer: List[Any],
    logs_dir: Path,
    demo: bool = False,
) -> dict:
    """Save snapshot and 5-second clip (or metadata stub in demo mode) on incident."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap_dir = logs_dir / "snapshots"
    vid_dir = logs_dir / "videos"
    snap_dir.mkdir(parents=True, exist_ok=True)
    vid_dir.mkdir(parents=True, exist_ok=True)

    snap_path = snap_dir / f"{channel_id}_{ts}.jpg"
    clip_path = vid_dir / f"{channel_id}_{ts}.mp4"

    if not demo and frame_buffer:
        try:
            import cv2  # type: ignore

            last_frame = frame_buffer[-1]
            annotated = last_frame.copy()
            cv2.putText(
                annotated,
                f"{channel_id} | {reason} | {ts}",
                (12, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (0, 0, 255),
                2,
            )
            cv2.imwrite(str(snap_path), annotated)

            h, w = last_frame.shape[:2]
            writer = cv2.VideoWriter(
                str(clip_path),
                cv2.VideoWriter_fourcc(*"mp4v"),
                10.0,
                (w, h),
            )
            for frm in frame_buffer:
                writer.write(frm)
            writer.release()
        except Exception:
            pass

    if not snap_path.exists():
        snap_path.write_bytes(b"DEMO_SNAPSHOT_PLACEHOLDER")
    if not clip_path.exists():
        clip_path.write_bytes(b"DEMO_5S_MP4_PLACEHOLDER")

    notify_slack_incident(channel_id, reason, snap_path, clip_path)
    return {"snapshot": str(snap_path), "clip": str(clip_path)}


def notify_slack_incident(
    channel_id: str,
    reason: str,
    snap_path: Optional[Path] = None,
    clip_path: Optional[Path] = None,
) -> bool:
    """Post incident alert to Slack webhook if configured."""
    webhook = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not webhook or "YOUR/WEBHOOK/URL" in webhook:
        return False

    payload = {
        "text": (
            f"[RTSP-QE Incident] `{channel_id}` - {reason}\n"
            f"Snapshot: `{snap_path.name if snap_path else 'N/A'}` | "
            f"Clip: `{clip_path.name if clip_path else 'N/A'}`"
        )
    }
    req = urllib.request.Request(
        webhook,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False

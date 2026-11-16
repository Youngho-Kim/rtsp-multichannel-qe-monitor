"""Credential pool matching for discovered IP cameras."""

from __future__ import annotations

import os
from typing import List, Optional, Tuple


DEFAULT_POOL = "admin:SecurePass123!,admin:4321,admin:admin,root:pass"


def load_credential_pool() -> List[Tuple[str, str]]:
    """Parse CAMERA_CREDENTIAL_POOL from environment variables."""
    raw = os.getenv("CAMERA_CREDENTIAL_POOL", DEFAULT_POOL)
    pool: List[Tuple[str, str]] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if ":" in entry:
            user, password = entry.split(":", 1)
            pool.append((user.strip(), password.strip()))
    return pool


def match_camera_credentials(ip: str, demo: bool = False) -> Optional[Tuple[str, str]]:
    """Return matching (username, password) for a camera IP."""
    pool = load_credential_pool()
    if not pool:
        return None
    if demo:
        return pool[0]

    # When onvif-zeep is installed, attempt DeviceManagement authentication per credential.
    try:
        from onvif import ONVIFCamera  # type: ignore

        for user, password in pool:
            try:
                cam = ONVIFCamera(ip, 80, user, password)
                cam.devicemgmt.GetDeviceInformation()
                return (user, password)
            except Exception:
                continue
    except ImportError:
        # Fallback: return primary credential from pool for RTSP probing.
        return pool[0]

    return None

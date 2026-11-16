"""Extract RTSP stream URI via ONVIF GetStreamUri or fallback template."""

from __future__ import annotations

from typing import Optional


def extract_rtsp_uri(
    ip: str,
    username: str,
    password: str,
    port: int = 554,
    demo: bool = False,
) -> str:
    """Return RTSP URI for an IP camera."""
    if demo:
        return f"demo://rtsp/{ip}:554/stream1"

    try:
        from onvif import ONVIFCamera  # type: ignore

        cam = ONVIFCamera(ip, 80, username, password)
        media = cam.create_media_service()
        profiles = media.GetProfiles()
        if profiles:
            req = media.create_type("GetStreamUri")
            req.ProfileToken = profiles[0].token
            req.StreamSetup = {
                "Stream": "RTP-Unicast",
                "Transport": {"Protocol": "RTSP"},
            }
            uri_resp = media.GetStreamUri(req)
            uri: Optional[str] = getattr(uri_resp, "Uri", None)
            if uri and uri.startswith("rtsp://"):
                if "@" not in uri:
                    uri = uri.replace("rtsp://", f"rtsp://{username}:{password}@", 1)
                return uri
    except Exception:
        pass

    return f"rtsp://{username}:{password}@{ip}:{port}/stream1"

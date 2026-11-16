"""Parse RTSP monitor logs, generate 1-page Markdown report, and post to Slack."""

from __future__ import annotations

import argparse
import json
import os
import re
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


TELEMETRY_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?\[TELEMETRY\]\s+"
    r"channels=(?P<channels>\d+)\s+rx_mbps=(?P<rx>[\d.]+)\s+"
    r"nic_drop=(?P<nic_drop>\d+)\s+frame_drops=(?P<frame_drops>\d+)\s+"
    r"disk_free_pct=(?P<disk>[\d.]+)"
)
INCIDENT_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?\[INCIDENT\]\s+"
    r"channel=(?P<channel>\S+)\s+reason=(?P<reason>.+)$"
)


def find_latest_log(logs_dir: Path) -> Optional[Path]:
    logs = sorted(logs_dir.glob("rtsp_multichannel_*.log"))
    return logs[-1] if logs else None


def parse_log_file(log_path: Path) -> Dict[str, object]:
    rx_values: List[float] = []
    nic_drops = 0
    frame_drops = 0
    disk_samples: List[float] = []
    channels_seen = 0
    incidents: List[Dict[str, str]] = []

    for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        m_tel = TELEMETRY_RE.match(line)
        if m_tel:
            channels_seen = max(channels_seen, int(m_tel.group("channels")))
            rx_values.append(float(m_tel.group("rx")))
            nic_drops += int(m_tel.group("nic_drop"))
            frame_drops += int(m_tel.group("frame_drops"))
            disk_samples.append(float(m_tel.group("disk")))
            continue

        m_inc = INCIDENT_RE.match(line)
        if m_inc:
            incidents.append({
                "timestamp": m_inc.group("ts"),
                "channel": m_inc.group("channel"),
                "reason": m_inc.group("reason").strip(),
            })

    return {
        "log_file": log_path.name,
        "samples": len(rx_values),
        "channels": channels_seen,
        "avg_rx_mbps": round(sum(rx_values) / len(rx_values), 2) if rx_values else 0.0,
        "peak_rx_mbps": round(max(rx_values), 2) if rx_values else 0.0,
        "total_nic_drops": nic_drops,
        "total_frame_drops": frame_drops,
        "min_disk_free_pct": round(min(disk_samples), 2) if disk_samples else 0.0,
        "incidents": incidents,
    }


def render_markdown_report(summary: Dict[str, object]) -> str:
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    incidents: List[Dict[str, str]] = summary["incidents"]  # type: ignore

    lines = [
        "# RTSP Multi-Channel Daily QA Report",
        f"- **Generated At:** {generated_at}",
        f"- **Source Log:** `{summary['log_file']}`",
        "",
        "## 1. Summary Metrics",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Monitored Channels | {summary['channels']} |",
        f"| Telemetry Samples | {summary['samples']} |",
        f"| Avg / Peak NIC Bandwidth | {summary['avg_rx_mbps']} / {summary['peak_rx_mbps']} Mbps |",
        f"| Total Frame Drops | {summary['total_frame_drops']} |",
        f"| NIC Drop Delta | +{summary['total_nic_drops']} |",
        f"| Min Disk Free | {summary['min_disk_free_pct']}% |",
        f"| Total Incidents | {len(incidents)} |",
        "",
        "## 2. Incident Timeline",
    ]
    if incidents:
        lines.append("| Timestamp | Channel | Reason |")
        lines.append("| --- | --- | --- |")
        for inc in incidents:
            lines.append(f"| {inc['timestamp']} | `{inc['channel']}` | {inc['reason']} |")
    else:
        lines.append("- No critical stream incidents detected.")

    return "\n".join(lines) + "\n"


def post_to_slack(markdown_text: str) -> bool:
    webhook = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if not webhook or "YOUR/WEBHOOK/URL" in webhook:
        return False

    req = urllib.request.Request(
        webhook,
        data=json.dumps({"text": markdown_text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def generate_report(log_file: Optional[str] = None, send_slack: bool = True, base_dir: Path = Path(".")) -> Path:
    logs_dir = base_dir / "logs"
    reports_dir = base_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    target = Path(log_file) if log_file else find_latest_log(logs_dir)
    if not target or not target.exists():
        raise FileNotFoundError("No rtsp_multichannel_*.log file found in logs/. Run monitor first.")

    summary = parse_log_file(target)
    md = render_markdown_report(summary)

    out_name = f"daily_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out_path = reports_dir / out_name
    out_path.write_text(md, encoding="utf-8")

    print(md)
    print(f"[REPORT] Saved: {out_path}")
    if send_slack:
        sent = post_to_slack(md)
        print(f"[SLACK] Posted: {'OK' if sent else 'SKIPPED (webhook not configured)'}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate 1-page RTSP daily QA report.")
    parser.add_argument("-f", "--file", help="Specific log file path")
    parser.add_argument("--no-slack", action="store_true", help="Do not post report to Slack")
    args = parser.parse_args()
    generate_report(log_file=args.file, send_slack=not args.no_slack)


if __name__ == "__main__":
    main()

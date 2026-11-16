"""HTML, CSV, and Slack report generator for RTSP multi-channel QE results."""

from __future__ import annotations

import csv
import html
import json
from datetime import datetime
from pathlib import Path

from camera_profile_validator import ProfileValidationResult
from stream_resilience_tester import ResilienceMetrics


def export_csv_report(
    validations: list[ProfileValidationResult],
    resilience: list[ResilienceMetrics],
    output_path: str | Path,
) -> Path:
    """Export combined profile validation and resilience metrics to CSV."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    res_map = {r.vendor: r for r in resilience}

    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "Vendor",
                "Model",
                "Profile Status",
                "Codec",
                "Resolution",
                "FPS",
                "Availability (%)",
                "Frame Drop (%)",
                "Fault Count",
                "MTTR (sec)",
                "Mismatches",
            ]
        )
        for v in validations:
            r = res_map.get(v.vendor)
            measured = v.measured
            res_str = f"{measured.get('width', 0)}x{measured.get('height', 0)}"
            writer.writerow(
                [
                    v.vendor,
                    v.model,
                    v.status,
                    measured.get("codec", ""),
                    res_str,
                    measured.get("fps", 0),
                    r.availability_pct if r else "",
                    r.frame_drop_rate_pct if r else "",
                    r.fault_count if r else "",
                    r.mttr_sec if r else "",
                    "; ".join(v.mismatches) if v.mismatches else "None",
                ]
            )
    return path


def export_html_report(
    validations: list[ProfileValidationResult],
    resilience: list[ResilienceMetrics],
    output_path: str | Path,
) -> Path:
    """Generate a self-contained HTML QA report suitable for Jira or README."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    res_map = {r.vendor: r for r in resilience}

    total = len(validations)
    passed = sum(1 for v in validations if v.status == "PASS")
    warned = sum(1 for v in validations if v.status == "WARN")
    failed = sum(1 for v in validations if v.status == "FAIL")
    avg_avail = (
        round(sum(r.availability_pct for r in resilience) / len(resilience), 2)
        if resilience
        else 0.0
    )

    rows_html = []
    for v in validations:
        r = res_map.get(v.vendor)
        badge_cls = {
            "PASS": "badge-pass",
            "WARN": "badge-warn",
            "FAIL": "badge-fail",
        }.get(v.status, "badge-warn")
        measured = v.measured
        mismatch_text = (
            "<br>".join(html.escape(m) for m in v.mismatches)
            if v.mismatches
            else "All checks passed"
        )
        rows_html.append(
            f"<tr>"
            f"<td><strong>{html.escape(v.vendor)}</strong><br><small>{html.escape(v.model)}</small></td>"
            f"<td><span class='badge {badge_cls}'>{html.escape(v.status)}</span></td>"
            f"<td>{html.escape(str(measured.get('codec', '-')))}</td>"
            f"<td>{measured.get('width', 0)}x{measured.get('height', 0)} @ {measured.get('fps', 0)}fps</td>"
            f"<td>{r.availability_pct if r else '-'}%</td>"
            f"<td>{r.mttr_sec if r else '-'}s</td>"
            f"<td>{mismatch_text}</td>"
            f"</tr>"
        )

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html_doc = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>RTSP Multi-Channel QE Report</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; background: #f8fafc; color: #0f172a; }}
  h1 {{ margin-bottom: 4px; }}
  .meta {{ color: #475569; font-size: 14px; margin-bottom: 24px; }}
  .cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }}
  .card {{ background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }}
  .card .label {{ font-size: 12px; color: #64748b; text-transform: uppercase; }}
  .card .value {{ font-size: 24px; font-weight: 700; margin-top: 6px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; }}
  th, td {{ padding: 12px 14px; text-align: left; border-bottom: 1px solid #e2e8f0; font-size: 14px; }}
  th {{ background: #f1f5f9; font-weight: 600; }}
  .badge {{ padding: 3px 8px; border-radius: 999px; font-size: 12px; font-weight: 600; }}
  .badge-pass {{ background: #dcfce7; color: #166534; }}
  .badge-warn {{ background: #fef9c3; color: #854d0e; }}
  .badge-fail {{ background: #fee2e2; color: #991b1b; }}
</style>
</head>
<body>
  <h1>RTSP Multi-Channel QE Verification Report</h1>
  <div class="meta">Generated at {generated_at}</div>
  <div class="cards">
    <div class="card"><div class="label">Total Channels</div><div class="value">{total}</div></div>
    <div class="card"><div class="label">Pass / Warn / Fail</div><div class="value">{passed} / {warned} / {failed}</div></div>
    <div class="card"><div class="label">Avg Availability</div><div class="value">{avg_avail}%</div></div>
    <div class="card"><div class="label">Resilience Checks</div><div class="value">{sum(r.total_checks for r in resilience)}</div></div>
  </div>
  <table>
    <thead>
      <tr>
        <th>Vendor / Model</th>
        <th>Status</th>
        <th>Codec</th>
        <th>Stream Spec</th>
        <th>Availability</th>
        <th>MTTR</th>
        <th>Findings</th>
      </tr>
    </thead>
    <tbody>
      {"".join(rows_html)}
    </tbody>
  </table>
</body>
</html>"""
    path.write_text(html_doc, encoding="utf-8")
    return path


def build_slack_summary(
    validations: list[ProfileValidationResult],
    resilience: list[ResilienceMetrics],
) -> str:
    """Build a JSON payload ready for Slack incoming webhooks."""
    passed = sum(1 for v in validations if v.status == "PASS")
    failed = sum(1 for v in validations if v.status == "FAIL")
    avg_mttr = (
        round(sum(r.mttr_sec for r in resilience) / len(resilience), 3)
        if resilience
        else 0.0
    )
    payload = {
        "text": (
            f"*[RTSP QE Summary]* Total: {len(validations)} | "
            f"PASS: {passed} | FAIL: {failed} | Avg MTTR: {avg_mttr}s"
        )
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
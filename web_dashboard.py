"""Built-in dark-mode Web Control Center for rtsp-multichannel-qe-monitor (http://127.0.0.1:8890)."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote


BASE_DIR = Path(__file__).resolve().parent
LOGS_DIR = BASE_DIR / "logs"
CAMERAS_FILE = BASE_DIR / "cameras.json"
ACTIVE_SERVER: Optional[ThreadingHTTPServer] = None
LAST_CLIENT_SEEN: float = time.monotonic()

DEMO_CAMERAS: List[Dict[str, str]] = [
    {"id": "CH01", "name": "Demo-Lobby (가상)", "ip": "192.168.10.101", "rtsp_url": "demo://rtsp/192.168.10.101:554/stream1"},
    {"id": "CH02", "name": "Demo-Gate (가상)", "ip": "192.168.10.102", "rtsp_url": "demo://rtsp/192.168.10.102:554/stream1"},
    {"id": "CH03", "name": "Demo-Parking (가상)", "ip": "192.168.10.103", "rtsp_url": "demo://rtsp/192.168.10.103:554/stream1"},
    {"id": "CH04", "name": "Demo-Warehouse (가상)", "ip": "192.168.10.104", "rtsp_url": "demo://rtsp/192.168.10.104:554/stream1"},
]

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


def _is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
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


def _read_pid_status(pid_file: Path) -> Dict[str, Any]:
    if not pid_file.exists():
        return {"running": False, "pid": None}
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        return {"running": _is_pid_running(pid), "pid": pid}
    except Exception:
        return {"running": False, "pid": None}


def collect_dashboard_state() -> Dict[str, Any]:
    live_cameras: List[Dict[str, str]] = []
    if CAMERAS_FILE.exists():
        try:
            raw_cams = json.loads(CAMERAS_FILE.read_text(encoding="utf-8")).get("cameras", [])
            live_cameras = [
                c for c in raw_cams
                if c.get("rtsp_url") and not str(c.get("rtsp_url")).startswith("demo://")
            ]
        except Exception:
            live_cameras = []

    latest_log = None
    if LOGS_DIR.exists():
        logs = sorted(LOGS_DIR.glob("rtsp_multichannel_*.log"))
        if logs:
            latest_log = logs[-1]

    latest_telemetry: Dict[str, Any] = {
        "timestamp": "-",
        "channels": len(live_cameras),
        "rx_mbps": 0.0,
        "nic_drop": 0,
        "frame_drops": 0,
        "disk_free_pct": 0.0,
    }
    incidents: List[Dict[str, str]] = []
    recent_lines: List[str] = []
    mode = "IDLE"

    if latest_log and latest_log.exists():
        lines = latest_log.read_text(encoding="utf-8", errors="ignore").splitlines()
        recent_lines = lines[-20:]
        for line in lines:
            if "[START]" in line:
                mode = "VIRTUAL-DEMO" if "VIRTUAL-DEMO" in line else "LIVE-RTSP"
            m_tel = TELEMETRY_RE.match(line)
            if m_tel:
                latest_telemetry = {
                    "timestamp": m_tel.group("ts"),
                    "channels": int(m_tel.group("channels")),
                    "rx_mbps": float(m_tel.group("rx")),
                    "nic_drop": int(m_tel.group("nic_drop")),
                    "frame_drops": int(m_tel.group("frame_drops")),
                    "disk_free_pct": float(m_tel.group("disk")),
                }
                continue
            m_inc = INCIDENT_RE.match(line)
            if m_inc:
                incidents.append({
                    "timestamp": m_inc.group("ts"),
                    "channel": m_inc.group("channel"),
                    "reason": m_inc.group("reason").strip(),
                })

    wd_status = _read_pid_status(LOGS_DIR / "watchdog.pid")
    mon_status = _read_pid_status(LOGS_DIR / "monitor.pid")
    is_running = wd_status["running"] or mon_status["running"]

    shown_cameras = DEMO_CAMERAS if (is_running and mode == "VIRTUAL-DEMO") else live_cameras

    snapshots: List[str] = []
    snap_dir = LOGS_DIR / "snapshots"
    if snap_dir.exists():
        snapshots = [p.name for p in sorted(snap_dir.glob("*.jpg"), reverse=True)[:8]]

    return {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": mode if is_running else "IDLE",
        "watchdog": wd_status,
        "monitor": mon_status,
        "cameras": shown_cameras,
        "telemetry": latest_telemetry,
        "incidents": list(reversed(incidents[-10:])),
        "incident_count": len(incidents),
        "snapshots": snapshots,
        "log_file": latest_log.name if latest_log else "-",
        "recent_logs": recent_lines,
    }


def execute_manage_action(action: str) -> Dict[str, Any]:
    if action == "shutdown_server":
        execute_manage_action("stop")
        if ACTIVE_SERVER is not None:
            threading.Thread(target=ACTIVE_SERVER.shutdown, daemon=True).start()
        return {"ok": True, "message": "웹 제어 센터와 모니터링을 모두 종료했습니다. 브라우저 탭을 닫으셔도 됩니다."}

    action_map = {
        "start_demo": [sys.executable, "manage.py", "start", "--demo"],
        "start_live": [sys.executable, "manage.py", "start"],
        "discover_live": [sys.executable, "manage.py", "start", "--discover"],
        "stop": [sys.executable, "manage.py", "stop"],
        "report": [sys.executable, "manage.py", "report", "--no-slack"],
        "clean": [sys.executable, "manage.py", "clean", "--days", "7", "--dry-run"],
    }
    cmd = action_map.get(action)
    if not cmd:
        return {"ok": False, "message": f"Unknown action: {action}"}

    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    res = subprocess.run(
        cmd,
        cwd=str(BASE_DIR),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=flags,
        timeout=30,
        check=False,
    )
    output = (res.stdout or res.stderr or "").strip()
    return {"ok": res.returncode == 0, "message": output or f"Action '{action}' completed."}


HTML_PAGE = """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RTSP Multi-Channel QE Monitor</title>
  <style>
    :root {
      --bg: #0f172a; --card: #1e293b; --border: #334155;
      --text: #f8fafc; --muted: #94a3b8; --accent: #38bdf8;
      --ok: #22c55e; --warn: #f59e0b; --err: #ef4444;
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: 'Segoe UI', 'Malgun Gothic', sans-serif; background: var(--bg); color: var(--text); padding: 20px; }
    .container { max-width: 1180px; margin: 0 auto; }
    header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 14px; margin-bottom: 16px; flex-wrap: wrap; gap: 10px; }
    h1 { margin: 0; font-size: 20px; color: var(--accent); }
    .meta { font-size: 13px; color: var(--muted); }
    .controls { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }
    button { border: 1px solid var(--border); background: var(--card); color: var(--text); padding: 9px 14px; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; transition: 0.15s; }
    button:hover { border-color: var(--accent); color: var(--accent); }
    button.btn-primary { background: #0284c7; border-color: #0284c7; color: #ffffff; }
    button.btn-primary:hover { background: #0369a1; color: #ffffff; }
    button.btn-danger { background: rgba(239,68,68,0.16); border-color: var(--err); color: #fca5a5; }
    button.btn-danger:hover { background: rgba(239,68,68,0.3); color: #ffffff; }
    .toast { display: none; background: #020617; border: 1px solid var(--accent); border-radius: 8px; padding: 10px 14px; margin-bottom: 16px; font-size: 13px; white-space: pre-wrap; color: #e2e8f0; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; margin-bottom: 20px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
    .kpi-label { font-size: 12px; color: var(--muted); margin-bottom: 6px; }
    .kpi-value { font-size: 22px; font-weight: 700; }
    .badge { display: inline-block; padding: 3px 9px; border-radius: 999px; font-size: 12px; font-weight: 700; }
    .badge-ok { background: rgba(34,197,94,0.18); color: var(--ok); }
    .badge-stop { background: rgba(239,68,68,0.18); color: var(--err); }
    .badge-mode { background: rgba(56,189,248,0.18); color: var(--accent); }
    .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
    @media (max-width: 860px) { .two-col { grid-template-columns: 1fr; } }
    h2 { font-size: 15px; margin: 0 0 10px 0; color: var(--text); }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); word-break: break-all; }
    th { color: var(--muted); font-weight: 600; }
    pre { margin: 0; background: #020617; border: 1px solid var(--border); border-radius: 8px; padding: 12px; font-size: 12px; line-height: 1.5; max-height: 260px; overflow-y: auto; color: #cbd5e1; }
    .snaps { display: flex; flex-wrap: wrap; gap: 8px; }
    .snap-link { color: var(--accent); text-decoration: none; font-size: 12px; background: #0f172a; border: 1px solid var(--border); padding: 5px 9px; border-radius: 6px; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>RTSP Multi-Channel QE Monitor</h1>
        <div class="meta">웹 제어 센터 · 실시간 스트리밍 상태 · 대역폭 · 장애 증적 (모니터링 중지 후 창을 닫으면 서버도 자동 종료)</div>
      </div>
      <div class="meta">
        <span id="modeBadge" class="badge badge-mode">IDLE</span>
        &nbsp;Updated: <span id="updatedAt">-</span>
      </div>
    </header>

    <div class="controls">
      <button class="btn-primary" onclick="runAction('start_demo')">▶ 가상 카메라 데모 시작</button>
      <button onclick="runAction('start_live')">▶ 실장비 모니터링 시작</button>
      <button onclick="runAction('discover_live')">🔍 ONVIF 탐색 후 시작</button>
      <button class="btn-danger" onclick="runAction('stop')">⏹ 모니터링 중지</button>
      <button onclick="runAction('report')">📄 일일 리포트 생성</button>
      <button onclick="runAction('clean')">🧹 7일 초과 로그 확인</button>
      <button class="btn-danger" onclick="runAction('shutdown_server')">⏻ 웹 제어 센터 종료</button>
    </div>

    <div id="toastBox" class="toast"></div>

    <div class="grid">
      <div class="card">
        <div class="kpi-label">Watchdog / Monitor</div>
        <div class="kpi-value" style="font-size:15px; line-height:1.7;">
          Watchdog: <span id="wdStatus" class="badge badge-stop">STOPPED</span><br>
          Monitor: <span id="monStatus" class="badge badge-stop">STOPPED</span>
        </div>
      </div>
      <div class="card">
        <div class="kpi-label">NIC 수신 대역폭 (rx_mbps)</div>
        <div class="kpi-value" id="rxMbps">0.00 Mbps</div>
      </div>
      <div class="card">
        <div class="kpi-label">프레임 드랍 / NIC 드랍</div>
        <div class="kpi-value"><span id="frameDrops">0</span> <span style="font-size:13px;color:var(--muted)">/ +<span id="nicDrop">0</span></span></div>
      </div>
      <div class="card">
        <div class="kpi-label">디스크 여유 / 누적 인시던트</div>
        <div class="kpi-value"><span id="diskFree">0%</span> <span style="font-size:13px;color:var(--muted)">/ <span id="incCount">0</span>건</span></div>
      </div>
    </div>

    <div class="two-col">
      <div class="card">
        <h2>연결 카메라 목록 (cameras.json)</h2>
        <table>
          <thead><tr><th>ID</th><th>이름</th><th>스트림 주소</th></tr></thead>
          <tbody id="camBody"></tbody>
        </table>
      </div>
      <div class="card">
        <h2>최근 장애 인시던트 &amp; 스냅샷</h2>
        <table>
          <thead><tr><th>시각</th><th>채널</th><th>원인</th></tr></thead>
          <tbody id="incBody"></tbody>
        </table>
        <div style="margin-top:12px;">
          <div class="kpi-label">저장된 스냅샷 (클릭해 확인)</div>
          <div id="snapList" class="snaps"></div>
        </div>
      </div>
    </div>

    <div class="card">
      <h2>실시간 로그 (<span id="logName">-</span>)</h2>
      <pre id="logTail">로그 대기 중...</pre>
    </div>
  </div>

  <script>
    let stopped = false;
    async function runAction(action) {
      const box = document.getElementById('toastBox');
      box.style.display = 'block';
      box.textContent = '실행 중... (' + action + ')';
      try {
        const res = await fetch('/api/action', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action })
        });
        const data = await res.json();
        box.textContent = data.message || '완료되었습니다.';
        if (action === 'shutdown_server') {
          stopped = true;
          return;
        }
        setTimeout(refresh, 400);
      } catch (e) {
        box.textContent = '요청 실패: ' + e;
      }
    }

    async function refresh() {
      if (stopped) return;
      try {
        const res = await fetch('/api/status');
        const d = await res.json();
        document.getElementById('updatedAt').textContent = d.updated_at;
        document.getElementById('modeBadge').textContent = d.mode;

        const wd = document.getElementById('wdStatus');
        wd.textContent = d.watchdog.running ? `RUNNING (${d.watchdog.pid})` : 'STOPPED';
        wd.className = 'badge ' + (d.watchdog.running ? 'badge-ok' : 'badge-stop');

        const mon = document.getElementById('monStatus');
        mon.textContent = d.monitor.running ? `RUNNING (${d.monitor.pid})` : 'STOPPED';
        mon.className = 'badge ' + (d.monitor.running ? 'badge-ok' : 'badge-stop');

        document.getElementById('rxMbps').textContent = d.telemetry.rx_mbps + ' Mbps';
        document.getElementById('frameDrops').textContent = d.telemetry.frame_drops;
        document.getElementById('nicDrop').textContent = d.telemetry.nic_drop;
        document.getElementById('diskFree').textContent = d.telemetry.disk_free_pct + '%';
        document.getElementById('incCount').textContent = d.incident_count;

        document.getElementById('camBody').innerHTML = d.cameras.map(c =>
          `<tr><td><b>${c.id}</b></td><td>${c.name || '-'}</td><td>${c.rtsp_url}</td></tr>`
        ).join('') || '<tr><td colspan="3">등록된 실장비 카메라 없음 (가상 데모를 실행하거나 cameras.json에 주소를 등록하세요)</td></tr>';

        document.getElementById('incBody').innerHTML = d.incidents.map(i =>
          `<tr><td>${i.timestamp}</td><td><b>${i.channel}</b></td><td>${i.reason}</td></tr>`
        ).join('') || '<tr><td colspan="3">감지된 장애 없음</td></tr>';

        document.getElementById('snapList').innerHTML = d.snapshots.map(s =>
          `<a class="snap-link" href="/media/snapshots/${encodeURIComponent(s)}" target="_blank">${s}</a>`
        ).join('') || '<span class="meta">저장된 스냅샷 없음</span>';

        document.getElementById('logName').textContent = d.log_file;
        const pre = document.getElementById('logTail');
        pre.textContent = d.recent_logs.join('\\n') || '로그 대기 중...';
        pre.scrollTop = pre.scrollHeight;
      } catch (e) {
        console.error(e);
      }
    }
    refresh();
    setInterval(refresh, 2000);
  </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def do_GET(self) -> None:  # noqa: N802
        global LAST_CLIENT_SEEN
        LAST_CLIENT_SEEN = time.monotonic()

        if self.path == "/" or self.path.startswith("/?"):
            body = HTML_PAGE.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/api/status":
            body = json.dumps(collect_dashboard_state(), ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path.startswith("/media/snapshots/"):
            fname = unquote(self.path.split("/media/snapshots/", 1)[1])
            target = (LOGS_DIR / "snapshots" / Path(fname).name).resolve()
            if target.exists() and target.is_file():
                data = target.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def do_POST(self) -> None:  # noqa: N802
        global LAST_CLIENT_SEEN
        LAST_CLIENT_SEEN = time.monotonic()

        if self.path == "/api/action":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
                action = str(payload.get("action", ""))
            except Exception:
                action = ""
            result = execute_manage_action(action)
            body = json.dumps(result, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.OK if result["ok"] else HTTPStatus.BAD_REQUEST)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")


def _idle_watchdog(server: ThreadingHTTPServer, idle_timeout: float) -> None:
    while ACTIVE_SERVER is server:
        time.sleep(1.5)
        if (time.monotonic() - LAST_CLIENT_SEEN) < idle_timeout:
            continue
        wd = _read_pid_status(LOGS_DIR / "watchdog.pid")
        mon = _read_pid_status(LOGS_DIR / "monitor.pid")
        if not wd["running"] and not mon["running"]:
            server.shutdown()
            break


def run_server(
    host: str = "127.0.0.1",
    port: int = 8890,
    open_browser: bool = True,
    idle_timeout: float = 10.0,
) -> None:
    global ACTIVE_SERVER, LAST_CLIENT_SEEN
    url = f"http://{host}:{port}"
    try:
        server = ThreadingHTTPServer((host, port), DashboardHandler)
    except OSError:
        if open_browser:
            webbrowser.open(url)
        return

    ACTIVE_SERVER = server
    LAST_CLIENT_SEEN = time.monotonic()
    if idle_timeout > 0:
        threading.Thread(target=_idle_watchdog, args=(server, idle_timeout), daemon=True).start()

    if sys.stdout is not None:
        print(f"[WEB] Dashboard running at {url} (Press Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        ACTIVE_SERVER = None
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Start RTSP QE Monitor Web Control Center.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8890, help="Bind port (default: 8890)")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open browser")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()

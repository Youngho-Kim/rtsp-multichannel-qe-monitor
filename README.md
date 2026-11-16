# RTSP Multi-Channel QE Monitor (`rtsp-multichannel-qe-monitor`)

IP 카메라 및 IoT 브릿지 게이트웨이의 장기 영상 스트리밍 건전성(Stability), 패킷 유실률, 네트워크 병목을 24/7 무인 자동 검증하기 위한 QE 자동화 파이프라인입니다.
**웹 제어 센터(`web_dashboard.py`)**를 기본 인터페이스로 제공하여 브라우저에서 가상 데모/실장비 모니터링 시작·중지·대역폭·인시던트·스냅샷·일일 리포트를 원클릭으로 제어할 수 있습니다.

## 주요 기능

* **웹 제어 센터 (`http://127.0.0.1:8890`):** 브라우저에서 가상 데모 시작, 실장비 모니터링 시작/중지, 리포트 생성, 실시간 로그 및 스냅샷 확인을 원클릭으로 수행합니다.
* **ONVIF 장비 자동 탐색 (WS-Discovery):** IP를 수동 입력하지 않아도 동일 서브넷 망 내 카메라를 자동 검색합니다.
* **다중 계정 풀 인증 (Credential Pool):** 제조사별 기본 계정 및 테스트 계정 풀을 순회하여 RTSP URI를 자동 추출합니다.
* **초경량 프레임 모니터링:** `cap.grab()` 중심 설계 및 다운스케일(640x360) 링 버퍼를 적용하여 다채널 수신 시 CPU/RAM 오버헤드를 절감합니다.
* **증적 자동 확보 & Slack 업로드:** 단절 및 대량 프레임 드랍 감지 시 장애 직전 5초 MP4 클립과 워터마크 스냅샷을 저장하고 Slack 채널에 자동 전송합니다.
* **하드웨어 및 네트워크 병목 감시:** 호스트 NIC 수신 대역폭(Mbps), 패킷 드랍, 디스크 잔여 용량(10% 미만 비상 청소 트리거)을 동시 추적합니다.
* **프로세스 자가 복구 (Watchdog):** 프로세스 크래시 발생 시 3초 이내 자동 재시작하며, 무한 재부팅(Crash-loop) 방어 장치를 포함합니다.
* **1페이지 요약 리포트 자동화:** 무인 가동 후 프레임 유실 통계, NIC 피크 대역폭, 인시던트 타임라인을 마크다운 리포트로 생성하고 Slack에 포스팅합니다.

## 프로젝트 구조

```text
rtsp-multichannel-qe-monitor/
├── open_dashboard.bat           # [웹 기본 실행] 더블클릭으로 웹 제어 센터 즉시 실행 (Windows)
├── web_dashboard.py             # [웹 제어 센터] 실행/중지/상태/로그/스냅샷 실시간 대시보드
├── manage.py                    # [통합 CLI] 시작/중지/상태/청소/리포트/웹 단일 진입점
├── setup.bat / setup.sh         # [환경 구성] Windows / Linux 원클릭 설치 스크립트
├── run_monitor.bat              # [Windows 메뉴] 터미널 대화형 실행 메뉴
├── run_pipeline.py              # 탐색 -> URI 추출 -> cameras.json 갱신 파이프라인
├── rtsp_multichannel_monitor.py # 멀티채널 RTSP 모니터링 및 가상 데모 엔진
├── watchdog.py                  # 프로세스 감시 및 자가 치유(Self-Healing) 데몬
├── generate_daily_report.py     # 로그 파싱, 1페이지 리포트 마크다운 생성 및 Slack 포스팅
├── cleanup_logs.py              # 7일 초과 스냅샷/비디오 자동 삭제 유틸리티
├── credential_matcher.py        # 카메라 계정 풀 순회 인증 모듈
├── discover_onvif.py            # WS-Discovery 기반 로컬 카메라 탐색기
├── extract_onvif_rtsp.py        # ONVIF GetStreamUri 기반 RTSP 추출 모듈
├── video_clip_recorder.py       # 장애 직전 5초 비디오 클립 생성 및 업로더
├── disk_guard.py                # 디스크 용량 감시 모듈
├── network_bandwidth_monitor.py # NIC 대역폭 및 패킷 드랍 감시 모듈
├── cameras.json                 # 활성 채널 목록 및 RTSP URL 설정 파일
├── .env.example                 # 슬랙 토큰 및 카메라 계정 설정 예시
├── logs/                        # 일별 런타임 로그, snapshots/, videos/
└── reports/                     # 생성되는 일일 요약 리포트 (.md)
```

## 빠른 시작 (웹 제어 센터 중심)

### 1. 원클릭 환경 구성

* **Windows 11:** `setup.bat` 더블클릭 (내부적으로 `python -m pip install -r requirements.txt` 실행 및 `.env` 생성)
* **macOS / Linux:**
  ```bash
  bash setup.sh
  source venv/bin/activate
  ```

### 2. 웹 제어 센터 실행 (기본 권장)

* **Windows 11:** `open_dashboard.bat` 더블클릭
* **macOS / Linux / 터미널:**
  ```bash
  python manage.py web
  ```
브라우저가 열리면 상단 버튼(**가상 카메라 데모 시작 / 실장비 모니터링 시작 / 모니터링 중지 / 일일 리포트 생성**)으로 모든 기능을 바로 제어하고 결과를 실시간으로 확인할 수 있습니다.

### 3. 환경변수(.env) 설정 (실제 장비 & Slack 연동 시)

```ini
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
SLACK_CHANNEL_ID=C0123456789
CAMERA_CREDENTIAL_POOL=admin:SecurePass123!,admin:4321,admin:admin,root:pass
```

## CLI 명령어 가이드 (`manage.py`)

```bash
# 웹 제어 센터 실행 (http://127.0.0.1:8890)
python manage.py web

# 기존 cameras.json 기반 백그라운드 가동 / ONVIF 탐색 후 가동
python manage.py start
python manage.py start --discover

# 가상 카메라 데모 모드 실행
python manage.py start --discover --demo --duration 6

# 실행 상태 점검 / 안전 종료
python manage.py status
python manage.py stop

# 일일 요약 리포트 생성 / 오래된 로그 정리
python manage.py report --no-slack
python manage.py clean --days 7 --dry-run
```

## 결함 분석 가이드 (Troubleshooting)

| 현상 | 원인 격리 기준 | 조치 사항 |
| --- | --- | --- |
| **전 채널 동시 프레임 드랍** | NIC 수신 대역폭이 85~95Mbps에 근접한 경우 | 100Mbps 스위치 링크 대역폭 포화 상태입니다. 1Gbps 스위치로 교체하거나 카메라 비트레이트(CBR)를 하향합니다. |
| **전 채널 동시 스트림 단절** | NIC 수신량이 0에 가깝고 재연결 실패가 반복되는 경우 | PoE 허브 전원 차단 또는 업링크 스위치 케이블 접촉 불량입니다. |
| **특정 채널만 지속 단절/드랍** | 타 채널 정상 수신, NIC 대역폭 및 호스트 CPU 여유 | 해당 카메라 펌웨어 프리징, 렌즈 IR 모듈 과열, 또는 해당 포트 랜선 결함입니다. (첨부된 5초 MP4 클립 확인) |
| **NIC Drop 카운트 증가** | 리포트에 `NIC Drop: +N`이 기록된 경우 | OS 커널 소켓 버퍼 부족입니다. `sudo sysctl -w net.core.rmem_max=16777216` 적용이 필요합니다. |

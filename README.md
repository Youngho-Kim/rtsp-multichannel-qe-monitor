# RTSP Multi-Channel QE Monitor (`rtsp-multichannel-qe-monitor`)

IP 카메라 및 IoT 브릿지 게이트웨이의 장기 영상 스트리밍 건전성(Stability), 제조사별 스트림 스펙 호환성, 장애 복구 시간(MTTR) 및 네트워크 병목을 24/7 자동 검증하기 위한 QE 자동화 파이프라인입니다.
**웹 제어 센터(`web_dashboard.py`)**를 기본 인터페이스로 제공하여 브라우저에서 가상 데모/실장비 모니터링, 제조사 스펙·MTTR 검증, HTML/CSV QA 리포트 확인까지 원클릭으로 제어할 수 있습니다.

## 실무 활용 시나리오 (Why This Tool?)

* **신규 카메라 연동 호환성 검증 공수 절감:** 새 IP 카메라 모델이 입고될 때마다 수동으로 VLC를 열어 코덱·FPS를 확인하는 대신, `camera_profiles.json`에 기대 스펙만 추가하면 `ffprobe` 기반으로 `PASS / WARN / FAIL`을 자동 판정합니다.
* **야간·주말 무인 에이징(Aging) 테스트:** 퇴근 후 다채널 카메라를 연결해 두고 다음 날 출근해 HTML/CSV 리포트로 채널별 가용률(%), MTTR(평균 복구 시간), 장애 타임라인을 즉시 확인합니다.
* **개발팀 이슈 커뮤니케이션 단축:** 단순 "영상 끊김" 보고가 아니라 장애 직전 5초 클립·스냅샷과 당시 호스트 NIC 대역폭(Mbps)·패킷 드랍 로그를 함께 첨부해 카메라 문제인지 네트워크 병목인지 빠르게 격리합니다.

## 주요 기능

* **웹 제어 센터 (`http://127.0.0.1:8890`):** 브라우저에서 가상 데모 시작, 실장비 모니터링 시작/중지, 스펙·MTTR 검증 실행, 실시간 로그 및 HTML/CSV 리포트 확인을 원클릭으로 수행합니다.
* **제조사별 호환성 프로파일 검증 (`camera_profile_validator.py`):** Hikvision·Hanwha Vision·Dahua 등 모델별 기대 코덱·해상도·FPS·GOP 스펙(`camera_profiles.json`)과 실제 스트림을 대조해 `PASS` / `WARN` / `FAIL`을 판정합니다.
* **장애 복구 시간(MTTR) & 가용률 측정 (`stream_resilience_tester.py`):** 단절 및 프레임 드랍 발생 시 재연결 시도 횟수, 평균 복구 시간(MTTR), 채널별 가용률(%)을 정량 측정합니다.
* **티켓 첨부용 HTML/CSV/Slack 리포트 (`qe_report_generator.py`):** Jira 이슈나 개발팀 공유에 바로 첨부할 수 있는 HTML 리포트, 엑셀 호환 CSV(UTF-8-SIG), Slack 요약 JSON을 자동 생성합니다.
* **ONVIF 장비 자동 탐색 & 다중 계정 풀 인증:** 동일 서브넷 내 카메라 자동 검색(WS-Discovery) 및 계정 풀 순회 RTSP URI 추출을 지원합니다.
* **초경량 모니터링 & 자가 복구 Watchdog:** `cap.grab()` 기반 링 버퍼(640x360), 장애 직전 5초 MP4 클립/스냅샷 저장, NIC 대역폭·디스크 10% 미만 비상 정리, 3초 내 프로세스 자가 복구를 제공합니다.

## 프로젝트 구조

```text
rtsp-multichannel-qe-monitor/
├── open_dashboard.bat           # [웹 기본 실행] cmd 창 없이 웹 제어 센터 즉시 실행 (Windows)
├── web_dashboard.py             # [웹 제어 센터] 실행/중지/스펙검증/로그/스냅샷/리포트 대시보드
├── manage.py                    # [통합 CLI] start/stop/status/report/clean/qe-suite/web
├── run_qe_suite.py              # [QE 검증 스위트] 제조사 스펙 대조 + MTTR 측정 + HTML/CSV 생성
├── camera_profile_validator.py  # [스펙 검증기] ffprobe 기반 코덱/해상도/FPS/GOP 대조
├── stream_resilience_tester.py  # [복원력 테스트] 단절 장애 시뮬레이션 및 MTTR·가용률 계산
├── qe_report_generator.py       # [리포트 생성기] HTML, CSV(UTF-8-SIG), Slack JSON 출력
├── test_qe_upgrade.py           # [단위 테스트] 프로파일 판정 및 리포트 생성 자동화 테스트
├── camera_profiles.json         # 제조사/모델별 기대 스트림 스펙 정의 파일
├── setup.bat / setup.sh         # [환경 구성] Windows / Linux 원클릭 설치 스크립트
├── run_monitor.bat              # [Windows 메뉴] 터미널 대화형 실행 메뉴
├── run_pipeline.py              # ONVIF 탐색 -> URI 추출 -> cameras.json 갱신
├── rtsp_multichannel_monitor.py # 멀티채널 RTSP 모니터링 및 가상 데모 엔진
├── watchdog.py                  # 프로세스 감시 및 자가 치유(Self-Healing) 데몬
├── generate_daily_report.py     # 런타임 로그 파싱 일일 마크다운 리포트 생성
├── cleanup_logs.py              # 7일 초과 스냅샷/비디오/로그 정리 유틸리티
├── credential_matcher.py        # 카메라 계정 풀 순회 인증 모듈
├── discover_onvif.py            # WS-Discovery 기반 로컬 카메라 탐색기
├── extract_onvif_rtsp.py        # ONVIF GetStreamUri 기반 RTSP 추출 모듈
├── video_clip_recorder.py       # 장애 직전 5초 클립·스냅샷 저장 및 Slack 전송
├── disk_guard.py                # 디스크 용량 감시 모듈
├── network_bandwidth_monitor.py # NIC 대역폭 및 패킷 드랍 감시 모듈
├── cameras.json                 # 실장비 카메라 목록 설정 파일
└── .env.example                 # 슬랙 토큰 및 카메라 계정 풀 예시
```

## 빠른 시작 (웹 제어 센터 중심)

### 1. 원클릭 환경 구성

* **Windows 11:** `setup.bat` 더블클릭 (`python -m pip install -r requirements.txt` 및 `.env` 생성)
* **macOS / Linux:**
  ```bash
  bash setup.sh
  source venv/bin/activate
  ```

### 2. 웹 제어 센터 실행 (기본 권장)

* **Windows 11:** `open_dashboard.bat` 더블클릭 *(창 없이 브라우저만 열림)*
* **macOS / Linux / 터미널:**
  ```bash
  python manage.py web
  ```
브라우저 상단 버튼으로 **가상 카메라 데모 시작 / 실장비 시작 / 스펙·MTTR 검증 리포트 / 일일 리포트 생성 / 중지**를 바로 실행하고 결과를 확인할 수 있습니다.

## CLI & 단위 테스트 가이드

```bash
# 제조사 프로파일 검증 + MTTR 측정 + HTML/CSV 리포트 생성 (데모 모드)
python manage.py qe-suite --demo

# 단위 테스트 실행
python -m unittest test_qe_upgrade.py -v

# 백그라운드 모니터링 / 상태 확인 / 중지 / 일일 리포트
python manage.py start --demo
python manage.py status
python manage.py stop
python manage.py report --no-slack
```

## 결함 분석 가이드 (Troubleshooting)

| 현상 | 원인 격리 기준 | 조치 사항 |
| --- | --- | --- |
| **전 채널 동시 프레임 드랍** | NIC 수신 대역폭이 85~95Mbps에 근접한 경우 | 100Mbps 스위치 링크 대역폭 포화 상태입니다. 1Gbps 스위치로 교체하거나 카메라 비트레이트(CBR)를 하향합니다. |
| **전 채널 동시 스트림 단절** | NIC 수신량이 0에 가깝고 재연결 실패가 반복되는 경우 | PoE 허브 전원 차단 또는 업링크 스위치 케이블 접촉 불량입니다. |
| **특정 채널만 지속 단절/드랍** | 타 채널 정상 수신, NIC 대역폭 및 호스트 CPU 여유 | 해당 카메라 펌웨어 프리징, 렌즈 IR 모듈 과열, 또는 해당 포트 랜선 결함입니다. (첨부된 5초 MP4 클립 확인) |
| **NIC Drop 카운트 증가** | 리포트에 `NIC Drop: +N`이 기록된 경우 | OS 커널 소켓 버퍼 부족입니다. `sudo sysctl -w net.core.rmem_max=16777216` 적용이 필요합니다. |

## 현재 적용 범위 및 확장 계획 (Scope & Roadmap)

* **현재 즉시 활용 가능한 범위:** 테스트 랩 내 소규모 다채널(4~8채널) IP 카메라 야간 안정성 에이징 검증, 제조사 스펙 대조, 단절 증적·HTML/CSV 리포트 자동화
* **대규모·사내 서버 확장 시 고도화 포인트:**
  * 30채널 이상 고해상도 동시 감시를 위한 멀티프로세싱/비동기 워커 분리
  * 비표준 ONVIF/Digest 인증 예외 처리 및 사내 장비 풀 맞춤형 튜닝
  * Linux 테스트 서버 상시 가동용 `systemd` 서비스 등록 및 사내 Jira REST API 자동 티켓 발행 연동

# GPT → Google Drive → Android Tablet 자동 동기화

## 목적
ChatGPT 예약이 검증한 공개 TCG JSON 스냅샷을 Google Drive `TCG_Grader_Sync/to_tablet`에 올리고,
Lenovo/Termux 태블릿이 **12시간마다 1회(태블릿 현지시간 08:00 / 20:00)** 확인하여
해시·스키마·프로젝트 게이트를 통과한 경우에만 17개 공개 런타임 JSON을 반영합니다.

## 안전 규칙
- 허용 파일은 `tablet_collection_publish.py`와 동일한 17개 공개 JSON만 허용
- manifest/main SHA가 태블릿 GitHub main과 정확히 일치해야 함
- tar.gz 안의 symlink/path traversal/추가 파일 거부
- 파일별 SHA-256/크기/JSON 파싱 검증
- 임시 worktree에서 `static_data_publish_gate.py`, 거래단위 최신성 검증 gate, `grading_company_updates.json` 검증 후에만 실제 반영
- 기존 데이터 전체 백업 + backup SHA-256 재검증 후 교체
- 서버가 살아 있는데 launcher PID를 확인할 수 없으면 live replacement 금지(HOLD)
- 서버 정상 종료 후 반영하고 `/api/v135-health` 또는 `/api/health` 확인
- 실패 시 검증된 기존 데이터로 rollback 후 `FAILED_ROLLED_BACK` receipt 생성
- 성공 시 `TABLET_SYNC_OK` receipt를 Google Drive `receipts/`에 다시 업로드
- 강제종료/배터리 종료 뒤 남은 legacy lock은 다음 실행에서 자동 복구
- 적용 도중 강제종료를 대비해 inflight transaction을 기록하고 부팅 시 `00_TCG_GDRIVE_RECOVERY.sh`가 last-good을 먼저 복원
- wake-lock은 동기화/복구 실행 중에만 잡고 종료 시 해제

## 검증 패키지 생산자
`tablet_gdrive_publish.py`는 검증된 17개 JSON으로 태블릿 수신 계약과 정확히 일치하는 `TCG_VERIFIED_*.tar.gz` + `manifest_*.json`을 만듭니다.

생산자 안전 규칙:
- 최신 `origin/main`과 현재 HEAD가 정확히 일치할 때만 실제 패키지 생성/전송
- 17개 JSON의 파싱·크기·SHA-256을 먼저 확인
- 생산자 자체 검증에 태블릿 수신기의 `load_manifest`/`extract_bundle` 로직을 재사용하여 producer/consumer schema drift 차단
- 원격 파일은 `--immutable`로 create-only 전송하여 동일 이름 덮어쓰기 금지
- **bundle을 먼저, manifest를 마지막에 업로드**하여 manifest를 원격 commit marker로 사용
- 업로드 뒤 Drive에서 manifest와 bundle을 다시 내려받아 크기·SHA-256·압축 내부 파일을 read-back 검증
- 부분 업로드나 read-back 불일치가 있으면 성공으로 판정하지 않음

`source=chatgpt_automation`은 실제 ChatGPT 자동화 생산 경로에만 사용합니다. 태블릿에서 임의로 만든 로컬 자료를 이 provenance로 가장하지 않습니다.

## 장시간 수집 최신성
기본 `source_collection_stats.json`/`adaptive_collection_stats.json`의 point-in-time 최신성 기준은 **900초를 그대로 유지**합니다. 다만 전체 수집 자체가 15분을 넘는 경우에는 `tcg_live_data.json`의 cycle 시작, `auto_update_report.json`의 시작/종료, 전체 mandatory output 결과가 같은 bounded transaction임을 독립적으로 증명할 때만 해당 stale-health HIGH를 INFO로 전환합니다.

- 기준 자체를 900초보다 느슨하게 만들지 않음
- 서로 다른 run, 오래된 report, 누락된 mandatory 결과, 시간 역전/불일치는 계속 fail-closed
- 다른 HIGH/CRITICAL은 절대 이 규칙으로 제거하지 않음

## Beckett/BGS 유지보수 대응
Beckett canonical 주소가 공식적으로 `maintenance.beckett.com`으로 리디렉션되는 동안:
- 기존 BGS pricing/news는 degraded로 유지하고 last-good 구조화 값을 보존
- 유지보수 페이지는 별도의 `bgs-maintenance-status` 상태 소스로만 사용
- canonical Beckett 주소에서 시작해 실제 최종 host가 maintenance host일 때만 신뢰
- 유지보수 페이지의 텍스트를 BGS 가격/요금 사실로 승격하지 않음
- canonical pricing/news가 정상 복구되면 기존 parser 경로를 다시 사용

## 1회 설치
```bash
cd ~/.../-tcg-grader
bash TABLET_GDRIVE_SYNC_INSTALL.sh
```

설치기가 `rclone` 로그인이 필요하다고 표시하면:
```bash
rclone config
```
에서 `gdrive`라는 Google Drive remote를 만든 후 설치기를 다시 실행합니다.

기본 설치는 즉시 전체 동기화를 추가 실행하지 않습니다. 설치 직후 수동으로 1회 실행해야 할 특별한 경우에만:
```bash
TCG_GDRIVE_SYNC_RUN_NOW=1 bash TABLET_GDRIVE_SYNC_INSTALL.sh
```
를 사용합니다.

## Google Drive 구조
```
TCG_Grader_Sync/
  to_tablet/
  receipts/
  last_good/
  quarantine/
```

## Android/Termux 주의
- Termux:Boot를 설치했다면 앱 아이콘을 한 번 실행해야 부팅 실행 권한이 활성화됩니다.
- Android 기종에 따라 백그라운드 제한으로 Termux/crond가 종료될 수 있으므로 Termux와 Termux:Boot의 배터리 최적화를 `제한 없음`/`최적화 안 함`으로 설정하는 것을 권장합니다.
- 부팅 스크립트는 장시간 wake-lock을 유지하지 않습니다. 동기화 wrapper가 실행 중에만 wake-lock을 사용하고 종료 시 해제합니다.

## 환경변수
- `TCG_REPO_DIR`: 태블릿 저장소 경로
- `TCG_GDRIVE_REMOTE`: 기본 `gdrive`
- `TCG_GDRIVE_ROOT`: 기본 `TCG_Grader_Sync`

비밀키/OAuth client secret은 저장소나 동기화 payload에 저장하지 않습니다.

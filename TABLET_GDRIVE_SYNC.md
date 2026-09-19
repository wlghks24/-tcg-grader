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
- 임시 worktree에서 `static_data_publish_gate.py`, `collection_verification_gate.py`, `grading_company_updates.json` 검증 후에만 실제 반영
- 기존 데이터 전체 백업 + backup SHA-256 재검증 후 교체
- 서버가 살아 있는데 launcher PID를 확인할 수 없으면 live replacement 금지(HOLD)
- 서버 정상 종료 후 반영하고 `/api/v135-health` 또는 `/api/health` 확인
- 실패 시 검증된 기존 데이터로 rollback 후 `FAILED_ROLLED_BACK` receipt 생성
- 성공 시 `TABLET_SYNC_OK` receipt를 Google Drive `receipts/`에 다시 업로드
- 강제종료/배터리 종료 뒤 남은 legacy lock은 다음 실행에서 자동 복구
- 적용 도중 강제종료를 대비해 inflight transaction을 기록하고 부팅 시 `00_TCG_GDRIVE_RECOVERY.sh`가 last-good을 먼저 복원
- wake-lock은 동기화/복구 실행 중에만 잡고 종료 시 해제

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

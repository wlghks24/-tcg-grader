# GPT → Google Drive → Android Tablet 자동 동기화

## 목적
ChatGPT 예약이 검증한 공개 TCG JSON 스냅샷을 Google Drive `TCG_Grader_Sync/to_tablet`에 올리고,
Lenovo/Termux 태블릿이 15분마다 자동으로 확인하여 해시·스키마·프로젝트 게이트를 통과한 경우에만
17개 공개 런타임 JSON을 원자적으로 교체합니다.

## 안전 규칙
- 허용 파일은 `tablet_collection_publish.py`와 동일한 17개 공개 JSON만 허용
- manifest/main SHA가 태블릿 GitHub main과 정확히 일치해야 함
- tar.gz 안의 symlink/path traversal/추가 파일 거부
- 파일별 SHA-256/크기/JSON 파싱 검증
- 임시 worktree에서 `static_data_publish_gate.py`, `collection_verification_gate.py`,
  `grading_company_updates.json` 검증 후에만 실제 반영
- 기존 데이터 전체 백업 후 원자적 교체
- 서버를 정상 종료 후 반영하고 `/api/v135-health` 또는 `/api/health` 확인
- 실패 시 기존 데이터 복원 후 `FAILED_ROLLED_BACK` receipt 생성
- 성공 시 `TABLET_SYNC_OK` receipt를 Google Drive `receipts/`에 다시 업로드

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

## Google Drive 구조
```
TCG_Grader_Sync/
  to_tablet/
  receipts/
  last_good/
  quarantine/
```

## 환경변수
- `TCG_REPO_DIR`: 태블릿 저장소 경로
- `TCG_GDRIVE_REMOTE`: 기본 `gdrive`
- `TCG_GDRIVE_ROOT`: 기본 `TCG_Grader_Sync`

비밀키/OAuth client secret은 저장소나 동기화 payload에 저장하지 않습니다.

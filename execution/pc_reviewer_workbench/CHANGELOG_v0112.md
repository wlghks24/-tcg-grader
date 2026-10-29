# TCG PC Reviewer v0.11.2 (GPT 업로드 연계 / 전용 GitHub 복제본)

## 변경 사항

- `handoff_package.py`가 `review.json`, `architecture.json`, `REPAIR_PLAN.md` 등 보고서 근거를 허용 목록으로 선별하여, SHA-256 목록이 포함된 `TCG_GPT_HANDOFF_*.zip`을 제작합니다. 소스코드 원본, 환경 파일, 토큰을 무조건 포함하지 않습니다. 네트워크 전송은 하지 않으며 사용자가 ChatGPT에 직접 업로드합니다.
- `folder_monitor.py`: 로컬 코드 폴더의 크기·mtime·경로를 15초마다 확인, 변경 시 별도 보고서 폴더로 자동 정적검사를 요청합니다. OS 네이티브 실시간 이벤트가 아닌 폴링 방식이며 메타데이터 변경을 놓칠 수 있습니다.
- `github_mirror.py`: 별도 `~/TCG_Grader_Audit_Mirror`에 고정 GitHub 저장소 `wlghks24/-tcg-grader` main을 최초 명시 동의로 복제하고, 변경 없고 깨끗한 전용 복제본에서 `fetch` + `merge --ff-only`만 허용합니다. 작업 중인 사용자 Git 폴더는 수정하지 않습니다. 실시간 웹훅은 아니며 5분 간격 갱신 선택 가능 (앱 실행 중에만).
- `local_gui.py`: GPT ZIP 생성·전용 복제본 갱신·읽기 전용 변경 감시 선택 기능. 로컬 Ollama 기능은 선택 항목으로 남겨둡니다.
- `tests/test_handoff_live_v0112.py`: 오프라인 ZIP/해시/원본 보호/변경 감지/dirty 미러 차단 회귀.

## 주의

- 기존 v0.11.1은 검사 시점 스냅샷이며 **실시간 GitHub 자동 동기화가 없었습니다**.
- 새 프로그램도 PR·미병합 브랜치는 자동 포함하지 않습니다. `main`만 갱신합니다. 미병합 코드는 GitHub에서 별도 추적해 검토해야 합니다.
- 코드 품질 채점은 ChatGPT 검토 후 별도 진행합니다. ZIP 생성이 코드 오류를 고치거나 AI를 실행하지는 않습니다.
- Windows 실제 UI/네트워크/성능·GitHub 전체 CI는 이 ZIP만으로 검증했다고 주장하지 않습니다. Draft/HOLD.

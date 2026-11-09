# TCG PC 전체 검토·수정 후보·태블릿 전달 검증

이벤트·콜라보·영화·등급측정·HOT 카드·HOT BOX·예상시세·환율/원화뿐 아니라 저장소의 모든 추적 파일을 목록화합니다. 26개 영역은 분류 기준입니다. 실제 전체 기능 수나 기능 완성도 100%를 뜻하지 않습니다.

## Windows에서 시작

1. ZIP을 다운로드하고 **압축을 모두 푼 뒤** 실행합니다. 기존 TCG나 R43 폴더 위에 덮어쓰지 않습니다.
2. Python 3.11 이상과 Git이 필요합니다. 기존 PC에 설치되어 있으면 그대로 사용합니다.
3. 실제 AI 검토·수정안 생성은 **PC의 Codex CLI와 기존 ChatGPT 로그인**이 필요합니다. 없으면 설치/로그인 필요 상태를 보고서에 남깁니다. 프로그램이 도구를 자동 설치하거나 API 키를 만들지 않습니다.
4. `START_AI_REVIEW.cmd`를 더블클릭합니다. GitHub에서 정확한 PR HEAD를 새 작업 폴더로 받아 검사합니다. **기존 PC 원본이나 태블릿에서 실행 중인 소스를 바꾸지 않습니다.**
5. 결과 위치는 `%LOCALAPPDATA%\TCG_PC_Review`입니다. 최신 폴더의 `READ_RESULT.html`을 열면 됩니다. `LATEST.txt`에도 최신 폴더가 기록됩니다.

Codex가 설치되어 있다면 터미널에서 아래 명령으로 로그인 상태를 준비합니다. 계정 로그인은 본인이 완료해야 합니다.

```powershell
codex login
codex login status
```

GitHub에 새 Draft PR까지 자동 올리려면 GitHub CLI(`gh`)의 기존 로그인도 필요합니다. 없으면 결과와 패치를 PC에 보관하고 `HOLD_GITHUB_CLI_SETUP`으로 남깁니다. 토큰을 채팅에 넣지 않습니다.

```powershell
gh auth login
```

구성에 사용하는 공식 안내:

- [Codex CLI 시작](https://learn.chatgpt.com/docs/cli)
- [Codex 비대화형 실행](https://learn.chatgpt.com/docs/non-interactive-mode)
- [Windows 격리 실행](https://learn.chatgpt.com/docs/windows/windows-sandbox)
- [Git for Windows](https://git-scm.com/downloads/win)
- [GitHub CLI](https://cli.github.com/)
- [Python](https://www.python.org/downloads/windows/)

ChatGPT/Codex 계정의 이용 한도가 적용됩니다. API 키 방식으로 자동 전환하지 않습니다. 이 프로그램이 새 유료 API나 외부 클라우드 실행환경을 만들지는 않습니다.

## 실행기

| 파일 | 하는 일 |
|---|---|
| `START_AI_REVIEW.cmd` | 전수 목록·정적 분석 → 격리된 일부 기준 테스트 → 독립 3세션 검토 → 교차토론 → 구조화 수정안 → 격리 후보 테스트 → 재분석·재수정. 통과 후보만 Draft PR 생성 시도 |
| `START_CHECK_ONLY.cmd` | GitHub 자료·전체 파일 목록·Python AST·엄격 JSON 검사. 앱 테스트/AI/소스 수정 없음 |
| `CHECK_TABLET_RELEASE.cmd` | 승인된 main을 새로 받아 PC 전체 Python 검사와 필수 gate·현재 HEAD CI·자료보존 설치 경로 확인. 태블릿 설치는 수행하지 않음 |
| `STOP.cmd` | 중지 요청. 현재 제한시간이 있는 단계 종료 후 멈춤 |

기본은 최신 **PR #1098의 정확한 HEAD**를 사용합니다. V980~V984 보완이 포함된 개발 후보이며 승인된 태블릿 배포본이라는 뜻은 아닙니다. main 및 열린 PR의 HEAD도 별도로 기록하고 최근 V970~V989 수정안 최대 10개를 비교합니다. 다른 PR을 자동 병합하지 않습니다.

다른 PR/시간을 선택하려면 압축 푼 폴더에서 다음처럼 실행합니다.

```powershell
py -3 -X utf8 runner.py --ai --publish-draft --pr 1098 --rounds 3 --minutes 90
py -3 -X utf8 runner.py --static-only --pr 0
```

기본 최대 3회, 총 테스트/AI 반복 시간은 90분입니다. 자료를 받는 준비 작업은 별도입니다. 새 수정 근거가 없거나 보호 경로·한도·권한·시간 문제가 생기면 사유와 실제 진행 횟수를 기록하고 멈춥니다. 같은 내용을 무한 실행하거나 검사 실패를 통과로 바꾸지 않습니다.

## 검토·수정 범위와 판정

- 모든 추적 파일의 경로·해시·크기를 기록합니다. Python은 AST, JSON은 중복 키/비정상 수치까지 검사합니다. 그 외 텍스트는 읽기 확인, 큰 파일/바이너리는 목록화 범위임을 명시합니다.
- 호출 지도는 정적 탐색 후보입니다. 함수가 실제 실행되거나 화면에 연결되었다는 증거로 사용하지 않습니다.
- 세 독립 Codex 세션이 정확성, 자료/등급/시세, 보안/운영을 각각 검토하고 별도 세션이 반박·교차확인합니다. 같은 모델일 수 있으며 여러 모델/수백 명의 합의라고 표현하지 않습니다.
- 최초 자동수정은 `runner.py`의 **8개 정확한 수집/환율/시세 경로**와 새로운 `execution/pc_candidate_*.py`, 새로운 회귀 테스트로 제한합니다. 전체 나머지 기능은 검토·문제분해·수정 설계에 포함하지만 자동 적용 대상은 아닙니다.
- 기존 테스트·역사 successor·검증기·보안·등급 캘리브레이션·학습자료·설치기·제어기 자체는 자동 수정하지 않습니다. 해당 경로 문제는 검토 항목과 보류 사유로 남깁니다. 역사계약이 필요한 수정은 정식 successor 작업 전까지 보류됩니다.
- 모델은 읽기 전용에서 수정안을 JSON으로 제안합니다. 제어기가 기존 파일 해시·정확한 경로·중복·경로탈출·Windows 예약명/ADS·symlink/junction·크기를 확인하고 새 후보 복사본에만 적용합니다. 변경 파일의 manifest 바이트/해시만 갱신합니다.
- 후보에는 새 회귀 테스트가 필요합니다. 기존 테스트 삭제나 수정으로 통과시킬 수 없습니다. 검증은 별도 복사본에서 수행하고 실패 후보와 로그는 보존합니다.
- Codex의 PC OS 격리가 동작할 때만 앱/후보 테스트를 실행합니다. 명시된 최소 파일 접근과 네트워크 차단 설정을 사용하고 외부 canary 접근이 거절되는지 확인합니다. 미지원이면 `HOLD_SANDBOX_REQUIRED`입니다. 샌드박스가 필요한 최초 설정은 PC에서 완료해야 합니다.
- 새 회귀 → 지정 무결성/구조/보안/기존 전체검사 gate → 발견한 Python 테스트 전체 순서로 실행합니다. 개별 작업 최대 180초, 총 시간한도 초과 항목은 `NOT_RUN`입니다. 실행 0건/전부 건너뜀/전부 기대실패는 통과하지 않습니다.
- JavaScript/UI 동작, 실시간 외부 수집, 실제 등급 측정, 태블릿 성능은 Python 검사와 별개입니다. 이번 자동수정 허용 목록은 Python뿐이며, UI·캘리브레이션 변경은 추가 검증이 필요합니다.
- 점수는 실제 실행 영수증이 있는 작업의 통과 비율입니다. AI가 임의로 제품 품질이나 등급 정확도를 100점으로 매기지 않습니다.
- `LESSONS.json`은 원인·반례·수정/실패를 중복 통합한 PC 기록입니다. 이미지 학습/등급 모델 재학습이나 외부 데이터의 자동 승격이 아닙니다.

## GitHub·태블릿 반영

모든 후보 Python 검사/gate가 통과하고 테스트한 바이트가 그대로이며 원본 PR HEAD가 바뀌지 않았을 때만 새 브랜치와 Draft PR 생성을 시도합니다. main에 직접 쓰거나 force-push/자동 병합하지 않습니다. 새 커밋의 전체 CI는 다시 조회합니다. PC 통과는 GitHub CI 통과와 다릅니다.

**현재 태블릿 자동 설치까지 완료된 패키지는 아닙니다.** V976 자료보존 설치기는 특정 과거 커밋 계보만 허용합니다. V984 및 앞으로 생성되는 후보가 그대로 설치 가능한 것으로 취급하면 안 됩니다. 이 패키지는 `TABLET_HANDOFF.json`에서 다음을 검증·분리하고 필요한 후속 작업을 드러냅니다.

1. 테스트한 소스 바이트·실제 Git HEAD·승인된 main·CI HEAD 일치.
2. 필수 CI 계열 존재와 모든 현재 결과 성공. 누락·보류·실패·조회 실패는 보류.
3. 자료보존 설치기 존재 여부 및 **새 대상에 대한 적용 계약 검토 필요**.
4. 실제 태블릿 경로·현재 SHA·자동실행 writer·사진/JSON 백업 검증·설치 후 readback은 여전히 실기기 작업.

`READY_FOR_DEVICE_REVIEW`도 기기 검토를 시작할 소스 조건을 만족했다는 뜻이며 설치 승인이 아닙니다. 이 도구에는 `adb install`, `git reset --hard`, `git clean`, 사진 삭제, 원격 태블릿 제어 명령이 없습니다. 태블릿 전달/설치 계약 통합이 승인되기 전에는 자동 설치하지 않습니다.

## 상태를 읽는 법

| 상태 | 의미 |
|---|---|
| `HOLD_AI_SETUP` | PC Codex 실행 파일/ChatGPT 로그인이 준비되지 않음 |
| `HOLD_SANDBOX_REQUIRED` | PC OS 격리 미준비. 테스트와 후보 수락 미실행 |
| `REJECTED_TESTS` | 새 후보가 검사를 통과하지 못함. 기존 소스 유지, 실패 자료로 다음 수정안 검토 |
| `HOLD_PROTECTED_CHANGE` | 보호 경로·기존 해시·패치 조건 불일치 |
| `DRAFT_CI_PENDING` | 개발 후보 업로드, 새 HEAD CI 완료 전 |
| `HOLD_TABLET_HANDOFF` | main/CI/테스트/설치 경로 중 필요한 증거 미충족 |
| `HOLD_REVIEW_REQUIRED` | 수행한 검토 결과가 있음. 전체 승인·실기기 완료를 의미하지 않음 |

종료코드 2는 보고서에 보류 사유가 있다는 뜻입니다. 결과 HTML과 같은 폴더의 JSON/로그를 함께 확인합니다. 이 ZIP 작성 시 실제 Windows·Codex 로그인·Lenovo 실행은 확인되지 않았습니다. 지원 도구의 synthetic 회귀검증과 실차/태블릿 검증은 다릅니다.

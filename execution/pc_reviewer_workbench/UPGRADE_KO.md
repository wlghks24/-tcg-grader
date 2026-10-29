# v0.10.0 Architecture Review — 검토 기능 확장 후보

기존 v0.9.3의 한계는 실제였습니다. 현재 코드 검사는 Python/JSON 문법, 미구현 단서와 주석 오타 위주였고, 수정 후보도 주석/줄바꿈에 한정됐습니다. Git 분석을 두 번 실행해 동일해도 독립적인 논리 검증이나 기능 구현 완료 증거가 되지 않습니다.

## 추가한 실제 기능

- 현재 코드 검사에 함수/중첩 함수 이름, 위치, 호출 이름, 절대 import 후보 지도 연결
- AST 본문이 동일한 비단순 함수 후보와 바이트 동일 파일 그룹
- 절대 import 그래프의 역방향 전이 영향 후보(순환 종료 처리)
- 긴 함수와 분기 추정치 기반 분리 검토 후보
- 문법/JSON 중복 키(P0), 미구현·보안 단서(P1), 중복·복잡도(P2) 작업표
- 근거, 보호 파일 여부, 영향 후보, 다음 수정 절차와 회귀 검증 조건 출력
- 로컬 Git의 HEAD에 미포함된 브랜치와 커밋 수: 네트워크 갱신·PR/CI 검증과 구별
- 검색 가능한 architecture.html, 상세 architecture.json, REPAIR_PLAN.md
- GUI 보고서 열기 버튼, Git 2회 검사를 '재현성 검사'로 정정

## 사용

압축을 새 폴더에 풀고 START_HERE.cmd를 실행합니다. Python 3.10 이상과 Tkinter가 필요합니다. 기존 버전은 덮어쓰지 않습니다. INSTALL_PC.cmd는 새 별도 경로에 설치합니다.

검사할 실제 저장소 루트와 원본 밖의 새 보고서 폴더를 선택하고 **현재 코드 심층 검사**를 실행하세요. 완료 후 **완료된 보고서 열기** → **코드지도·중복·보완 작업표 열기**에서 검색할 수 있습니다. Git 이력 전수 재현성 검사는 별도 버튼입니다.

REPAIR_PLAN.md, architecture.json, review.json은 개발자/GPT가 같은 근거로 후속 수정을 검토하는 자료입니다. 원본 SHA-256은 review.json에 보존됩니다. 수정 후 새 결과 폴더로 다시 검사해야 합니다.

## 완성되지 않은 범위

이 패키지는 심층 정적 검토 확장판이며 모든 오류를 자동 수정하는 완성 AI가 아닙니다. 실행 경로, 데이터 흐름, 실제 요구사항 충족, 모델 학습 성능은 증명하지 않습니다. 호출 이름은 런타임 연결이 확인된 호출 그래프가 아닙니다. 상대/dynamic import, reexport는 영향 그래프에 미해결로 남습니다. 본문 동일성은 인자/데코레이터/전역값/closure가 같은 의미임을 보장하지 않습니다. 중복 삭제·함수 공통화·미구현 로직 생성·PR 병합은 자동 실행하지 않습니다.

Git 결과는 PC에 이미 존재하는 참조만 확인합니다. fetch하지 않으므로 GitHub 최신 PR/CI나 미병합 기능 전체를 확인했다고 해석하면 안 됩니다. 다른 언어는 Python AST 분석 대상이 아닙니다. 기존 Ruff는 설치된 경우 선택 실행하며 새 도구나 모델을 자동 설치하지 않습니다.

Windows GUI 실행·실제 대규모 TCG 전체 저장소 검사·GitHub 최신 CI 검증은 이 패키지의 현지 검증 범위에 포함되지 않습니다.

## 조사와 적용 판단 (2026-10-29)

외부 소스를 복사하거나 패키지를 추가하지 않고 Python 표준 AST로 위 기능을 직접 구현했습니다. 아래 도구는 이번 ZIP에 설치/내장하지 않았습니다. 성능 향상률이나 보안 감사 완료를 주장하지 않습니다.

|기술|확인한 공식 자료|이번 판단|
|---|---|---|
|Python AST|https://docs.python.org/3.12/library/ast.html|기본 구조 분석에 적용, 실행/의미 증명과 구별|
|Ruff|https://docs.astral.sh/ruff/linter/|기존 선택형 검사 유지. safe/unsafe fix 구분에 따라 무조건 자동 적용하지 않음|
|Pyright|https://github.com/microsoft/pyright|타입/심볼 검사 확장 후보. 현재 미통합·미시험|
|LibCST|https://github.com/Instagram/LibCST|MIT, 서식 보존 codemod 확장 후보. 현재 미통합·미시험|
|jscpd|https://github.com/kucherenko/jscpd|MIT, 다언어 중복 탐지 확장 후보. 현재 미통합·미시험|
|Sonar 공식 영상|https://www.youtube.com/watch?v=el9OKGrqU6o|검색 결과의 공식 설명 확인. 영상 전체 재생 검증은 하지 않음|
|Sonar 복잡도 설명|https://www.sonarsource.com/resources/cognitive-complexity/|함수 단위 검토 참고. 현재 분기 추정치는 Sonar Cognitive Complexity 구현이 아님|

외부 도구의 고정 버전·배포 의존성·Windows 호환성·성능은 도입 전 추가 시험이 필요합니다. 이번에는 이를 확인하지 않은 채 설치하지 않았습니다.

## GitHub 현재 상태를 확인한 범위

TCG PR #926 메타데이터를 읽었습니다. 조회 시 draft/open, head c7ad77f7ac8decbca4f27986ea20fb8b534a298b였습니다. 이는 프로그램 기능 시험용 전체 저장소 분석이 아닙니다. 이 작업에서는 프로젝트 main, PR, 무결성 계약 또는 태블릿을 수정하지 않았습니다.

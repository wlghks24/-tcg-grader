# TCG Grader · Graphify 코드 지도 (Android/Termux + ChatGPT/Codex)

## 먼저 확인할 점

이 프로젝트의 현재 태블릿 환경은 **Mac도 Windows도 아니고 Android + Termux**입니다.
따라서 Mac/Windows용 설치 명령을 그대로 쓰지 않고 Termux에 맞춰 설치합니다.

Graphify 공식 PyPI 패키지 이름은 `graphifyy`(y 두 개)이고 실행 명령은 `graphify`입니다.
Python 3.10 이상이 필요합니다.

> 중요: Graphify 공식 문서의 주요 지원 환경 목록에는 Android/Termux가 별도 플랫폼으로 명시되어 있지 않습니다. 이 저장소는 Linux 계열 CLI 동작을 Termux에 맞춰 감싼 것입니다. 따라서 GitHub Actions의 Linux 검증이 통과해도 **실제 태블릿 설치 성공 여부는 Termux에서 `graphify --version`과 최초 지도 생성까지 확인해야 최종 성공**으로 봅니다.

## 가장 쉬운 설치 방법

Termux에서 TCG 프로젝트 폴더 안에 있는 상태에서 아래 한 줄만 실행합니다.

```bash
bash SETUP_GRAPHIFY_TERMUX.sh
```

스크립트가 자동으로 다음 순서를 처리합니다.

1. Android/Termux 환경 확인
2. Python 3.10+ 확인
3. `uv`가 있으면 `uv tool install graphifyy`
4. `uv`가 없으면 `pipx install graphifyy` 방식 사용
5. `graphify --version` 검증
6. OpenAI Codex용 프로젝트 연동 (`graphify codex install --project`; 필요 시 `graphify install --project --platform codex`로 대체)
7. 최초 코드 지도 생성
8. `graphify hook install`로 커밋/브랜치 전환 시 자동 갱신 설정
9. 이 TCG 저장소 전용 `post-merge` 보조 훅으로 태블릿이 원격 `main`을 fast-forward로 받은 뒤에도 지도 자동 갱신

## 직접 한 단계씩 할 경우

### 1) Python 버전 확인

Termux에 붙여넣기:

```bash
python --version
```

`Python 3.10` 이상이면 다음 단계로 갑니다. Python이 없다면:

```bash
pkg update -y
pkg install python -y
```

### 2) Graphify 설치

`uv`가 이미 있다면:

```bash
uv tool install graphifyy
```

`uv`가 없다면 pipx 방식:

```bash
python -m pip install pipx
python -m pipx ensurepath
python -m pipx install graphifyy
```

설치 후 Termux를 다시 열거나 다음을 실행합니다.

```bash
export PATH="$HOME/.local/bin:$PATH"
source ~/.bashrc
```

### 3) 설치 확인

```bash
graphify --version
```

버전 번호가 나오면 CLI 설치는 정상입니다.

`graphify: command not found`가 나오면:

```bash
export PATH="$HOME/.local/bin:$PATH"
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
hash -r

graphify --version
```

`uv` 설치라면 추가로 다음도 사용할 수 있습니다.

```bash
uv tool update-shell
```

pipx 설치라면:

```bash
python -m pipx ensurepath
```

## ChatGPT/OpenAI에 맞춘 자동 지도 우선 사용

### 중요한 차이

**ChatGPT 모바일 앱 자체에는 태블릿의 로컬 `PreToolUse` 훅을 직접 실행하는 기능이 없습니다.**
따라서 OpenAI 계열에서 프로젝트 파일을 실제로 읽고 수정하는 로컬 코딩 환경은 **Codex 프로젝트 규칙**을 사용합니다.

TCG 프로젝트 폴더에서 한 번 실행:

```bash
graphify codex install --project
```

Graphify 버전에 따라 아래 형태도 같은 목적입니다.

```bash
graphify install --project --platform codex
```

이렇게 하면 Codex 쪽에서는 `AGENTS.md` 등 프로젝트 지침을 통해 코드 질문 전에 Graphify 지도를 우선 조회하도록 구성됩니다.

일반 Agent Skills 호환용도 함께 원하면:

```bash
graphify agents install --project
```

Codex에서 Graphify 스킬을 직접 호출하는 표기는 `/graphify`가 아니라 **`$graphify`** 입니다.

```text
$graphify .
```

## 최초 코드 지도 만들기

태블릿 Termux에서는 AI 슬래시 명령이 아니라 **CLI 명령**을 사용하는 것이 가장 확실합니다.

```bash
bash GRAPHIFY_UPDATE.sh
```

최초 실행 시 `graphify extract . --code-only`를 사용하여 코드 중심 로컬 AST 지도를 생성합니다. 코드만 분석하므로 API 키나 LLM 호출이 필요하지 않습니다.

생성 위치:

```text
graphify-out/
├── graph.html
├── GRAPH_REPORT.md
└── graph.json
```

- `graph.html`: 브라우저에서 보는 시각적 코드 지도
- `GRAPH_REPORT.md`: 구조/핵심 연결 요약
- `graph.json`: Graphify query가 사용하는 전체 그래프

## AI가 알아서 지도를 먼저 보게 하기

프로젝트 폴더에서 한 번 실행:

```bash
graphify codex install --project
graphify hook install
```

Codex에서는 Graphify 스킬을 직접 호출할 때 `/graphify`가 아니라 **`$graphify`** 문법을 사용합니다.

예:

```text
$graphify .
```

ChatGPT 앱에서 이 GitHub 프로젝트를 작업할 때는 `graphify-out/GRAPH_REPORT.md`와 `graph.json`이 저장소에 실제로 제공되어 있으면 코드 구조 참고 자료로 활용할 수 있습니다. 다만 ChatGPT 앱이 태블릿 로컬 훅을 직접 실행하거나 태블릿 로컬 `graphify-out` 파일을 자동으로 읽는 것은 아닙니다.

## 코드가 바뀌면 지도 갱신

### Termux 검은 창에서 직접 갱신

```bash
graphify update .
```

또는 이 프로젝트용 안전 래퍼:

```bash
bash GRAPHIFY_UPDATE.sh
```

이 저장소의 래퍼는 기존 그래프가 있으면 `graphify update . --force`를 사용합니다. `--force`는 리팩터링/파일 삭제 후 노드 수가 줄어드는 정상 상황에서도 새 지도를 반영하기 위한 Graphify 공식 옵션입니다. 지도는 원본 코드가 아니라 재생성 가능한 보조 산출물이므로, 실제 코드/학습자료를 덮어쓰지 않습니다.

### AI 스킬 안에서 변경분만 갱신

Claude/Gemini 등 `/graphify` 문법을 쓰는 환경:

```text
/graphify . --update
```

Codex:

```text
$graphify . --update
```

주의: Termux의 일반 쉘에서 `/graphify . --update`를 그대로 입력하는 것은 AI 스킬 호출 문법이므로 맞지 않습니다. Termux에서는 `graphify update .`를 사용합니다.

## 자동 갱신 범위 — 다시 확인한 정확한 동작

Graphify 자체의 `graphify hook install`은 **post-commit + post-checkout** 자동 갱신을 담당합니다. 공식 권장 흐름에서는 `git pull`/`git merge` 후에는 `graphify update .`를 별도로 실행해야 합니다.

TCG 태블릿은 GitHub 변경을 `git merge --ff-only origin/main`으로 받으므로, `SETUP_GRAPHIFY_TERMUX.sh`가 Graphify 공식 훅을 보존하면서 별도의 `post-merge` 래퍼를 설치합니다. 따라서 설치가 완료된 태블릿에서는:

- 직접 `git commit` → Graphify 공식 post-commit 훅 갱신
- 브랜치 `checkout/switch` → Graphify 공식 post-checkout 훅 갱신
- TCG 업데이터가 원격 `main` fast-forward → TCG 전용 post-merge 래퍼가 `GRAPHIFY_UPDATE.sh --quiet` 백그라운드 실행

으로 나뉩니다.

확인:

```bash
graphify hook status
```

TCG 원격 갱신 훅까지 직접 확인하려면:

```bash
grep -n TCG_GRAPHIFY_POST_MERGE .git/hooks/post-merge
```

`TCG_GRAPHIFY_POST_MERGE` 문구가 보이면 연결된 것입니다.

Graphify를 업그레이드한 뒤에는 훅에 기록된 실행 경로를 새로 맞추기 위해 다음 두 작업을 다시 실행하는 것이 안전합니다.

```bash
graphify hook install
bash SETUP_GRAPHIFY_TERMUX.sh
```

## TCG Grader용 적용 원칙

이 저장소에는 `.graphifyignore`를 두어 가격/행사/학습 결과처럼 계속 바뀌는 런타임 JSON과 등급사진 폴더를 코드 지도에서 제외합니다. 따라서 Graphify는 주로 Python/JavaScript/HTML/셸 스크립트와 안정적인 문서를 중심으로 구조를 분석합니다.

`graphify-out/cache/`, 비용정보와 Graphify 실행로그는 `.gitignore`에서 로컬 전용으로 유지합니다. `graph.html`, `GRAPH_REPORT.md`, `graph.json`은 필요할 때만 명시적으로 공유/커밋할 수 있도록 강제로 삭제하지 않습니다.

Graphify 지도는 **탐색 보조 자료**입니다. 코드를 실제로 수정할 때는 지도에서 관련 모듈을 먼저 좁힌 뒤 원본 코드를 다시 확인하고, 기존 TCG 안전 게이트·수동등록 자료·학습 데이터 보존 규칙을 그대로 지켜야 합니다.

## 최종 성공 판정

다음 네 가지가 모두 통과해야 태블릿 설치를 완료로 봅니다.

```bash
python --version
graphify --version
graphify hook status
ls -lh graphify-out/graph.html graphify-out/GRAPH_REPORT.md graphify-out/graph.json
```

마지막 `ls`에서 3개 파일이 모두 실제로 존재하고 크기가 0보다 크면 코드 지도 생성까지 완료된 것입니다.

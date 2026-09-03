# TCG Grader · Graphify 코드 지도 (Android/Termux + ChatGPT/Codex)

## 현재 적용 기준

이 프로젝트의 태블릿 환경은 **Android + Termux**입니다. Mac/Windows용 설명을 그대로 사용하지 않습니다.

- Python: **3.10 이상**
- PyPI 패키지: `graphifyy`
- 실행 명령: `graphify`
- 저장소 검증 버전: **0.9.53**
- 태블릿 설치: `SETUP_GRAPHIFY_TERMUX.sh`
- 지도 갱신/자가복구: `GRAPHIFY_UPDATE.sh` + `GRAPHIFY_SELF_HEAL.py`

> Android/Termux는 Graphify의 별도 공식 플랫폼으로 보장되는 환경이 아니므로, GitHub Actions 통과와 별개로 태블릿에서 `graphify --version` 및 실제 지도 생성까지 확인해야 최종 성공입니다.

## 가장 쉬운 설치

Termux에서 `-tcg-grader` 프로젝트 폴더 안에서 다음 한 줄을 실행합니다.

```bash
bash SETUP_GRAPHIFY_TERMUX.sh
```

스크립트는 다음을 자동 처리합니다.

1. Android/Termux 확인
2. Python 3.10+ 확인/설치
3. Graphify **0.9.53 고정 설치** (`uv` 우선, 없으면 `pipx`)
4. PATH 보정
5. `graphify --version` 정확한 버전 확인
6. 자가복구/학습 엔진 안전검사
7. Codex + Agent Skills 프로젝트 연동
8. 최초 코드 지도 생성
9. Graphify Git hook + TCG 전용 `post-merge` 자동 갱신 연결

## 직접 설치할 때

Python 확인:

```bash
python --version
```

Python이 없다면:

```bash
pkg update -y
pkg install python -y
```

`uv` 사용 시:

```bash
uv tool install --force 'graphifyy==0.9.53'
```

`uv`가 없으면:

```bash
python -m pip install pipx
python -m pipx ensurepath
python -m pipx install --force 'graphifyy==0.9.53'
```

PATH 오류가 있으면:

```bash
export PATH="$HOME/.local/bin:$PATH"
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
hash -r
```

설치 확인:

```bash
graphify --version
```

`0.9.53`이 확인되어야 현재 저장소 검증 버전과 일치합니다. 새 Graphify 버전은 태블릿에서 자동 채택하지 않고 GitHub Actions에서 먼저 검증한 뒤 저장소 기준 버전을 올립니다.

## OpenAI/Codex 연동

프로젝트 폴더에서 한 번 실행:

```bash
graphify codex install --project
graphify agents install --project
graphify hook install
```

Codex 스킬 호출은 `/graphify`가 아니라 **`$graphify`** 형식입니다.

```text
$graphify .
```

ChatGPT 모바일 앱 자체는 태블릿의 로컬 훅을 직접 실행하거나 로컬 `graphify-out`을 자동으로 읽지 않습니다. 로컬 코딩 에이전트 자동 지도 우선 사용은 Codex 프로젝트의 `AGENTS.md`/Graphify 스킬로 처리합니다.

## 지도 생성 및 갱신

TCG 프로젝트에서는 직접 Graphify 명령보다 안전 래퍼 사용을 권장합니다.

```bash
bash GRAPHIFY_UPDATE.sh
```

동작:

- 첫 실행: `graphify extract . --code-only`
- 기존 지도 존재: `graphify update . --force`
- `GRAPH_REPORT.md` 또는 `graph.html` 누락: `graphify cluster-only . --no-label`
- 모든 단계의 반환코드를 개별 검사
- `graph.json`, `GRAPH_REPORT.md`, `graph.html` 세 파일이 모두 0바이트보다 커야 성공

결과:

```text
graphify-out/
├── graph.html
├── GRAPH_REPORT.md
└── graph.json
```

## 오류 결과 학습 + 자가복구

`GRAPHIFY_UPDATE.sh`가 실패를 감지하면 `GRAPHIFY_SELF_HEAL.py`를 호출합니다.

현재 자동 분류 대상:

- `graphify: command not found` / PATH 문제
- 검증 버전 불일치
- `update` 실패
- `extract` 실패
- `cluster-only` 실패
- 필수 지도 산출물 누락
- Git hook 문제
- 분류되지 않은 일반 실패

복구 전략은 코드에 미리 승인된 것만 사용할 수 있습니다.

1. 기존 `graph.json`에서 보고서/HTML 재생성
2. 기존 지도를 `.graphify_recovery/`에 보존하고 전체 재생성
3. Graphify 0.9.53 재설치 후 전체 재생성
4. Git hook 재설치

성공/실패 결과는 기기 로컬 파일에 누적됩니다.

```text
graphify_self_heal_memory.json   # 오류종류별 성공한 복구전략 학습
graphify_self_heal_report.json   # 가장 최근 복구 상세결과
.graphify_recovery/              # 복구 전 기존 지도 보존
GRAPHIFY_UPDATE.log              # 실행 로그
```

같은 오류가 다시 발생하면 과거에 성공한 **검증된 전략을 먼저 시도**합니다.

### 안전 제한

자가학습 파일의 문자열을 셸 명령으로 실행하지 않습니다. 학습 결과가 임의 Python/셸 코드를 만들거나 저장소 코드를 자동 수정·커밋하는 기능도 없습니다. 따라서 학습 파일이 손상되거나 예상치 못한 값이 들어와도 `APPROVED_STRATEGIES`에 등록되지 않은 동작은 차단됩니다.

즉 여기서 말하는 자가학습은 **오류 원인 분류 + 검증된 복구전략 성공률 학습 + 다음 복구 순서 최적화**입니다. 실제 프로그램 소스 수정은 GitHub 검증을 거쳐 반영합니다.

## 자동 갱신

Graphify 기본 hook:

```bash
graphify hook install
graphify hook status
```

TCG 태블릿은 `git merge --ff-only origin/main`으로 업데이트되므로 설치 스크립트가 별도의 `post-merge` 브리지를 추가합니다.

확인:

```bash
grep -n TCG_GRAPHIFY_POST_MERGE .git/hooks/post-merge
```

원격 `main` fast-forward 후 `GRAPHIFY_UPDATE.sh --quiet`가 백그라운드로 실행되고, 실패하면 동일한 자가복구/학습 절차가 작동합니다.

## 코드 지도 범위

`.graphifyignore`에서 가격/행사/자가학습 결과/등급사진 등 고변동 런타임 자료를 제외하여 코드 구조 지도가 불필요하게 흔들리지 않도록 했습니다.

Graphify 지도는 탐색 보조 자료입니다. 코드를 수정할 때는 지도에서 관련 모듈을 좁힌 뒤 원본 소스를 다시 확인하고 TCG의 학습자료/수동등록사진/검증자료 보존 규칙을 유지해야 합니다.

## 최종 확인 명령

Termux에서 한 줄씩 실행합니다.

```bash
python --version
graphify --version
python GRAPHIFY_SELF_HEAL.py --self-test
graphify hook status
ls -lh graphify-out/graph.html graphify-out/GRAPH_REPORT.md graphify-out/graph.json
```

정상 판정:

- Python 3.10+
- Graphify 0.9.53
- `Graphify self-heal bounded-learning self-test: OK`
- hook 정상
- 지도 3개 파일 모두 존재하고 0바이트보다 큼

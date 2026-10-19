# 태블릿 코드 지도 V661 — 빠른 탐색·오류 진단·영향 분석

현재 공개 TCG Grader GitHub 코드에 추가하는 **읽기 전용** 태블릿 전용 인덱스입니다.
기존 대표 기능 검색入口 \`code_map_fast_route.py\` 및 Graphify를 교체하지 않습니다.

## GitHub 기준 구조 (main ff47c970)
파일명 기준: 전체 1,717개, Python 896개, 루트 파일 964개,
워크플로 128개, \`TCG_CROSSCHECK/\` 357개, 태블릿 자율진화 V371~V400
22개 버전(중간 번호는 연속되지 않음). 파일 목록 검사는 전체 대상이지만
모든 코드의 실행·논리 완전성이 검증되었다는 의미는 아닙니다.

| 기능 | 진입점 | 우선 확인할 코드와 보호장치 |
|---|---|---|
| 태블릿 구동·업데이트 | \`main\`, \`TABLET_SCHEDULED_UPDATE.sh\` | \`ANDROID_UPDATE_AND_START.sh\`, last-good |
| 실행 구성 | \`tablet_runtime_manifest.py\` | \`safe_runtime.py\`, Termux, PWA |
| AI 자율진화 | \`tablet_autonomous_evolution_v400.py\` | V399→이전 버전, V387 검증 차단 |
| 실제 학습 증거 | V374 / V375 / V376 / V373 | V381 표본·V387 신뢰도, 검증된 출처 |
| 가격·행사 수집 | \`tcg_updater_v135.py\` | 수집 실패·출처 신뢰·유효기간 |
| 코드 지도 | \`code_map_fast_route.py\` | \`code_map_intelligence.py\`, Graphify |
| 태블릿 지도 보강 | \`execution/tablet_code_atlas_v661.py\` | 추적 파일·Python AST·기존 테스트 |
| 계약·히스토리 | \`TCG_CROSSCHECK/\` | 삭제하지 않고 버전별 보호 |

## 명령 (태블릿/로컬 체크아웃에서)
\`\`\`bash
python -m execution.tablet_code_atlas_v661 --check
python -m execution.tablet_code_atlas_v661 --changed tablet_autonomous_evolution_v387.py
python -m execution.tablet_code_atlas_v661 --changed TABLET_SCHEDULED_UPDATE.sh
python -m execution.tablet_code_atlas_v661 --all
python code_map_fast_route.py "태블릿 자율진화 증거 부족" --impact
\`\`\`

반환값: 역할별 파일 수, 실사용 필수 파일 누락, 파싱 오류,
정적 의존성 경로, 변경 영향 후보, 기존 관련 테스트 및 CI 요구 수준.
\`--all\`은 상세 지도를 **표준 출력으로만** 제공합니다.
외부 패키지·유료 API·클라우드 학습은 필요하지 않습니다.
소스는 실행하지 않고 AST만 분석하므로 동적 import 및 반사 코드는
별도 검사가 필요합니다. 지도만으로 배포 승인·학습 신뢰도 증가 불가.

## 검토·토론·평가·채점·개선 루프

1. 문제의 **증거** 확보: 오류 로그, SHA, 수집 상태, 기기 영수증.
2. **코드 지도**로 기능 진입점·의존성·중복 후보·기존 테스트 식별.
3. **P0**(보안·데이터·구동) / **P1**(재발·테스트 부족) /
   **P2**(구조·성능)로 나누어 원인과 대안을 검토.
4. 수정 전 **반론·영향·롤백·무료 운용**을 검토하고 최소 패치.
5. 테스트 → 현 HEAD CI·CodeQL·무결성·동기화 계약 교차검증.
6. 95점 이상은 '승인 품질 목표'일 뿐 근거 없는 점수/임의 PASS 불가.
7. 실제 태블릿 실행 영수증은 CI와 분리 확인. 확인 전 HOLD.

버전별 \`tablet_autonomous_evolution_v*.py\` 및 \`TCG_CROSSCHECK\`
계약은 단순 중복이 아닙니다. **사용 중인지 의존성·테스트·사용자
승인이 확인되기 전에는 삭제·이동·병합 금지.** 지도는 런타임 소스,
학습 원본, 23:00 예약, Git 브랜치를 자동으로 변경하지 않습니다.

기존 PR #748도 \`integrity_manifest.json\`을 수정하므로
**두 PR의 병합 순서는 별도 검증**이 필요합니다. 빠른 forward-only
병합이 불가능하면 매니페스트 재계산과 현재 SHA 전체 CI 재검사.

## 복제 소스 및 스킬 미러 검사

`mirror_health`는 AGENTS/CLAUDE/GEMINI, `.agents/.codex/.github` 스킬 미러,
`ai_reliability_v8` 호환 복제 경로를 비교합니다. 내용이 다르면 REVIEW,
심볼릭 링크 등이 있으면 HOLD로 분류합니다. 별도 파일 이동·삭제·자동
동기화는 절대 수행하지 않습니다. 동일한 파일이라고 해서 불필요한 코드로
판정하지 않으며 기존 V387 학습 신뢰도에 반영하지 않습니다.

## Lenovo 로컬 파일 차이 진단 (읽기 전용)

`python -m execution.tablet_code_atlas_v661 --tablet-diff`
명령은 설치된 기기에서 Git HEAD의 `integrity_manifest.json`과
현재 활성 런타임 파일을 해시로 비교합니다. 변경·누락·위험 파일의
**이름과 개수**만 표시하며, 현재 파일 내용과 토큰을 공개하지 않습니다.
기준은 *해당 기기 로컬 HEAD*이고 원격 GitHub `main` 최신 여부와는
별개입니다. 변경이 있어도 자동 복원·덮어쓰기·삭제·학습 승인하지 않습니다.

보안 제한: `--tablet-diff`는 코드 지도 도구가 포함된 **정식 저장소
경로에서만 실행**되며, 임의의 `--root` 값을 외부 Git 명령의 실행
경로로 전달하지 않습니다.

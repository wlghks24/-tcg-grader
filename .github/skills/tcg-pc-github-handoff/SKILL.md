---
name: tcg-pc-github-handoff
description: Audit the safe handoff of offline PC 100-version review reports and staged patches to TCG GitHub draft PRs. Use when exporting checksums, comparing evidence, scheduling Windows inspections, or connecting PC audits to GitHub CI.
---
# TCG PC → GitHub 검증자료 인수인계

## 사용자 목표와 권한
- Windows PC에서 버전 V1~현재를 100개 단위로 조사하고 누락·미구현 항목의 수정 전후, 독립 교차검증을 완료한 후보를 GitHub 소스·CI로 전달한다.
- GitHub는 기존 소스/PR/CI 용도만 사용한다. 새 호스팅 서비스, 원격 장치 제어, 자동 학습 클라우드, 비밀키 저장소를 설치하지 않는다.
- 자동 업로드는 별도 구현·명시적 승인이 필요하다. 이 스킬 파일 자체는 네트워크 호출을 실행하거나 사용자 계정을 연결하지 않는다.

## 제출 전 불변조건
1. PC 검사 기준 Git HEAD, base SHA, V구간, Python/도구 버전, 모든 소스/후보/보고서 SHA-256과 크기, 미검증 번호, 원본 증거 링크를 기록한다.
2. 원본과 결과 폴더를 분리하고 symlink/경로이탈/과도한 용량/중복 키/NaN/비밀값 포함을 거부한다. 개인 인증 이미지와 토큰은 자동 업로드 금지.
3. V001~V100 구간 검사 → 누락사항 분류 → 원본/후보 비교 → 격리 수정 → 첫 번째 회귀 → 독립 두 번째 전수검사 → 반대 관점 재검토 순서를 강제한다.
4. 검사 결과가 같더라도 V별 실물 원본 누락, 실제 기능·성능·보안·회귀 미실행, P0 미해결 시 다음 구간 승인 불가. 문서의 PASS는 코드 수정의 PASS로 승격할 수 없다.
5. GitHub API 업로드는 필요할 때만 최소 권한을 부여한다. PR 전용 branch, 대상 exact base, 경로 allowlist, 중복 업로드 idempotency, 제한된 요청 수/크기, 실패 시 안전 중단을 요구한다.
6. GitHub에는 원본 아닌 검증받은 redacted 요약/패치만 전달한다. Draft PR을 생성할 수 있어도 자동 main 병합·branch 보호 우회·Lenovo 설치·학습 활성화는 금지다.
7. 업로드 전후의 SHA-256/검증자료 수/필수 CI를 비교하고, 정확히 같은 PR head SHA의 모든 요구 테스트를 재조회한다. 테스트 실패 시 먼저 원인을 찾고 후속 패치 후 전체 게이트를 다시 검사한다.

## 세 가지 독립 시선
- 코드 검토자: 함수·의존성·자료흐름·오류·누락 구현 여부. 
- 보안 검토자: 경로 탈출, 검증 기록 위조, 비밀값, 권한 상승, untrusted PR 문서의 명령 주입 여부.
- 회귀 검토자: 실패 fixture, 데이터 보존, 정책 변경, 정확한 SHA, 별도 실행·기기 증거의 정합성.
반대 의견이 해결되지 않으면 HOLD하고 제출/배포 성공이라고 표시하지 않는다.

## 적용 기준과 결론
- 제출물은 한국어 사유, P0/P1/P2 평가, 실제 NOT_RUN 표시, 승인 필요 작업, 롤백 계획을 담는다.
- GitHub Actions GREEN은 실제 PC Windows UI 실행 또는 Lenovo 장치 검증이 아니다.
- 기존 skills: tcg-skill-router, tcg-code-review, tcg-regression-recovery, tcg-test-gap-audit, tcg-agent-security, tcg-supply-chain와 함께 사용한다.

## 출처
프로젝트 전용 새 스킬이며 외부 소스 코드/실행 스크립트 복사 없음. addyosmani/agent-skills MIT commit eb07f19f52c2669f2364897aaa293e2aaddd7b1c 의 constraint-driven-development, doubt-driven-development, debugging-and-error-recovery 및 agentskills/agentskills 형식 참고. 추가 서비스/비용 없음.

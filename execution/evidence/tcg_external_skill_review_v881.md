# TCG Grader 외부 개발 스킬 적용 평가 (V881)

검토일: 2026-10-29. 목적: GitHub 공개 스킬을 참고해 TCG 카드 학습의 증거 보존과 정밀검사 절차를 보완한다. 외부 스크립트/플러그인 설치·코드 복제·클라우드 실행은 하지 않는다.

| 공식 저장소 | 라이선스·검토 기준 | 적합한 방법 | 결정 |
| --- | --- | --- | --- |
| https://github.com/obra/superpowers | MIT, 2026-10-29 공개 저장소 확인. 현재 릴리스/HEAD를 로컬에 고정해 실행하지 않았음 | test-driven-development, systematic-debugging, verification-before-completion의 원인 재현→최소 수정→정확한 HEAD 재검증 | 절차만 참고하여 프로젝트 전용 스킬로 재작성 |
| https://github.com/mattpocock/skills | MIT, 저장소 패키지 1.3.1 표시 확인. 외부 agent 설치 불필요 | 코드 리뷰 시 사용자 요구사항과 저장소 표준을 독립 교차확인; bug diagnosis와 TDD | 평가 기준만 참고, 자동 실행/서브에이전트 미도입 |
| https://github.com/anthropics/skills | 일부 Apache-2.0, 일부 문서 기능은 source-available 등 개별 라이선스 확인 필요 | SKILL.md와 독립 문서/테스트 분리 방식 | 일반 구조만 참고, 소스·스크립트 미도입 |

## 기존 스킬과 비교

기존 `tcg-code-review`, `tcg-regression-recovery`, `tcg-test-gap-audit`, `tcg-mistake-proofing`, `tcg-supply-chain`은 각각 필요하지만, 학습 증거의 복합적 읽기·저장·재학습 경로와 `verified` 우회 위험을 한 번에 점검하도록 설계되지 않았다. 이를 보완하기 위해 새 `.github/skills/tcg-learning-evidence-integrity/SKILL.md`를 등록했다.

## 적용 결과·보안 결정

- 새 도구 실행권/토큰/네트워크 권한 없음; 외부 저장소 콘텐츠는 신뢰할 수 없는 참고 자료로만 취급.
- `tcg-skill-router`가 P0 학습/증거 관련 변경을 전용 스킬로 라우팅.
- `execution/tests/test_learning_evidence_skill_v881.py`로 스킬 등록·독립 재검토 기준·실제 인증 불리언·카드 식별값 회귀를 검증.
- 수정 전후 증거, HTTPS API 저장 지속성, 여러 POST 동시성, 실제 Windows 환경 및 Lenovo 기기 검증은 별도 증거가 확보되기 전까지 **HOLD**.
- 기존 역사적 동기화 및 무결성 검사를 완화하거나, PR을 자동 병합하지 않는다.

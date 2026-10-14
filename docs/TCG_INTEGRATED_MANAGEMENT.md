# TCG Integrated Management Contract

## Stable system identity
- system_id: `TCG-INSTAGRAM-CARDINFO-INTEGRATED`
- user-facing automation title: `인스타 카드정보`
- scope: Pokémon TCG + ONE PIECE CARD GAME + NARUTO Card Game
- repository source of truth: `wlghks24/-tcg-grader` main branch

## Single-system rule
새 채팅 또는 새 대화가 시작되어도 별도 TCG 관리 시스템, 별도 TCG 자료수집 자동화,
별도 06:00 점검 자동화, 별도 10:00 제작 자동화, 별도 22:00 수정 자동화를 새로 만들지 않는다.

기존 `인스타 카드정보` 통합 자동화와 GitHub main의 통합 코드를 계속 업데이트한다.
새 기능은 반드시 이 시스템의 하위 단계로 추가하고, 중복 작업/중복 자동화가 생기지 않도록 한다.

## Integrated daily flow
1. 매 정각: 수집·검증·error_ledger/prevention_rule 갱신
2. 06:00 KST: Main 자료수집 상태 ↔ Instagram 카드정보 정확도 비교
   - `daily_collection_instagram_accuracy.py`
   - `COLLECTION_INSTAGRAM_ACCURACY_REPORT.json`
   - stale / repeated failure / source-health / 3×3 coverage / policy regression / factual conflict 검사
3. 10:00 KST: 검증된 데이터로 1080×1350 PNG 6장 + 본문 + 해시태그 생성
4. 22:00 KST: 10:00 baseline 대비 verified material diff가 있을 때만 수정판 생성
5. 모든 단계: X10THINK / SELFREFINE / upload-delivery gate / regression check 유지

## Cross-domain comparison rule
Main과 Instagram은 하나의 TCG 관리 시스템 안에서 비교하지만,
provider health, retry history, learning state, error ledger 같은 런타임 상태는 섞지 않는다.

교차검증은 `crosscheck_exchange/`의 passive factual JSON만 사용한다.
같은 `canonical_key`의 값이 충돌하면 평균내거나 임의 승격하지 않고 재검증한다.
candidate/corroborated가 상대편 verified 상태만으로 자동 verified가 되지 않게 한다.

## Source and repair rule
- 공식 사실: 공식 1차 출처 우선
- 실제 완료거래: 독립 underlying sale lineage 기준
- Market Reference와 completed sale 분리
- 403/429 우회 금지, Retry-After/backoff/승인된 대체 소스 사용
- 동일 오류 2회 이상: 동일 재시도 금지, source/filter/parser/normalization 중 최소 1개 변경
- 동일 오류 3회 이상: 주 경로 강등/격리 + 대체 경로 활성화
- 성공한 수정은 prevention_rule로 승격 후 회귀검사

## New-chat continuation rule
새 채팅에서 TCG 관련 요청이 들어오면:
1. 이 통합 시스템을 기존 시스템으로 간주한다.
2. 새 자동화를 만들기 전에 기존 `인스타 카드정보` 자동화를 조회·재사용한다.
3. 기존 main 코드/설정/디자인/06:00 감사/10:00 생성/22:00 diff 규칙을 이어서 수정한다.
4. 동일 목적의 자동화나 관리체계를 중복 생성하지 않는다.
5. Anime 자동화와는 계속 완전 분리한다.

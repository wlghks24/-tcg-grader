# TCG Grader 100+1000 정밀검증 인수인계 계약 v332

이 문서는 `wlghks24/-tcg-grader`의 TCG Grader 100+1000 정밀검증 후속 작업에서 반드시 유지할 운영·검증 기준을 고정한다.

## 1. Current-state-first

- 작업을 시작할 때마다 `main`의 최신 SHA, 열린 PR, 해당 head의 CI 상태를 다시 조회한다.
- 과거 채팅·기록의 PR 번호, SHA, CI 성공 결과를 현재 상태로 재사용하지 않는다.
- 오래된/open/diverged PR은 자동 병합하지 않는다. 최신 main 대비 중복·대체·충돌 여부와 exact-head CI를 다시 확인한다.
- protected main을 우회하지 않는다. direct main push, force push, unsafe reset/clean을 금지한다.

## 2. 100 + 1000 품질 프레임

- `100`은 실제 외부 100명 참여 주장이 아니라 100개의 독립 시니어 데이터 준비 관점이다.
- `1000`은 실제 외부 1000명 참여 주장이 아니라 25개 전문가군 × 40개 검토 렌즈 = 1000 review cells의 내부 QA 프레임이다.
- 순서: 자료 발견/수집 → 파싱 → 정규화 → 중복제거 → 오탈자·정체성 확인 → freshness → 출처 독립성 → 교차검증 → 반대증거 → 충돌 → gap 분석/보완 → prepared dataset → 1000-cell review → targeted tests → full regression → actual output validation → release/hold.
- 안전 blocker는 다수결로 무시할 수 없다.

## 3. 카드 판본·세대·가격 결합

- 파이프라인: 사진 → 판본(KR/JP/EN) → OCR → 카드명/번호/세트 → 세대/시리즈 → 결함 → 등급사별 예상등급 → PSA 8/9/10 확률 → RAW/PSA8/9/10 시세 → provenance/freshness → verified-learning → tablet/runtime.
- 게임(Pokémon/ONE PIECE/NARUTO), 판본/언어(KR/JP/EN), 판매시장(KR/JP/US), 상품유형(CARD/BOX/PACK), 카드번호, 세트, 희귀도, variant(base/parallel/manga/promo/first edition 등), 등급업체, 정확 등급이 맞을 때만 가격을 결합한다.
- 카드번호/세트 식별자가 부족한 name-only 검색은 집계 시세 또는 등급가를 생성하지 않는다.
- `UNKNOWN`은 자동확정하지 않는다. 세트코드·판본·레귤레이션 충돌은 `UNKNOWN/CONFLICT`로 유지한다.
- 시세가 부족하면 임의 가격을 생성하지 않는다.
- Pokémon 세대는 근거 있는 set/era에만 부여하고, ONE PIECE/NARUTO에 Pokémon 세대를 적용하지 않는다.

## 4. 환율

- 출처 timestamp/provenance가 있고 freshness가 검증된 유한한 양수 환율만 사용한다.
- 72시간이 지난 환율은 stale로 처리한다.
- 갱신 실패, 페이지/앱 복귀, focus, 만료 시 이미 렌더링된 stale KRW 환산 표시를 제거한다.

## 5. 등급사 공식소스

- PSA/BGS/CGC/TAG/BRG는 official-only, last-good, fail-closed를 유지한다.
- 401/403/404/429 및 host-policy 차단은 우회하지 않고 자동 allowlist 확대도 금지한다.
- timeout, connection reset, HTTP 502/503/504만 bounded retry를 허용한다.
- degraded 상태를 success로 표시하지 않는다.

## 6. 결함분석·학습

- 결함분석은 전체 → 4분할 → 8분할 순으로 수행하고 최악 구역을 최종 판단에 반영한다.
- PSA/BGS/CGC/TAG/BRG의 기준을 분리한다.
- 실제 사용자 확인 또는 신뢰 경계가 충족된 검증 행만 verified-learning으로 승격한다.
- KR/JP/EN visual learning을 분리한다.
- 미검증 후보, 참고 데이터, 과거 verified 표시는 현재 검증 없이 자동승격하지 않는다.

## 7. Tablet/Termux 수집·배포

- 최신 main 기준에서만 수집한다.
- 허용된 공개 JSON만 receipt/SHA-256/commit-clean/freshness 검증 후 PR-only로 전달한다.
- 개인 사진, 인증키, 운영 폴더, 코드 혼입을 금지한다.
- 사용자 실제 태블릿/Termux 실행, GitHub 인증, 실물 사진 육안검증은 실제 증거 없이 완료로 승격하지 않는다.
- 단일 main 진입점, candidate preflight, ff-only update, final verification을 유지한다.

## 8. Tablet GPT ↔ TCG Grader 교차검증

- 양쪽의 학습/운영 규칙은 검증된 delta/receipt를 통해 교차확인한다.
- watched path가 verified delta 이후 변경되었는데 새 검증 delta가 없으면 `TABLET_GPT_SYNC_STALE`로 fail-closed 처리한다.
- stale snapshot을 현재 정렬 상태로 간주하지 않는다.

## 9. 검증 순서

최소 순서는 다음과 같다.

1. targeted tests
2. subsystem/related regression
3. full regression
4. runtime/integrity/security 검증
5. actual output validation
6. exact-head CI 확인
7. release 또는 hold

테스트 assertion, allowlist, fail-on-degraded, 보안 경계를 약화해 통과시키지 않는다.

## 10. 완료 판정

- 문서상 계획, 해시 일치, 과거 로그만으로 실제 기능 완료를 선언하지 않는다.
- main 반영 여부, exact-head CI, 실제 출력/런타임 증거를 분리해서 기록한다.
- 외부 장애나 접근제한이 남으면 해결된 것으로 표시하지 않는다.
- 현재 기준을 변경할 때는 새로운 버전의 인수인계 계약으로 명시적으로 갱신한다.

## 기준 시점

- 이 문서를 만든 기준 main: `6c54ab50b04ae772b22dea143937e7c8becdee07` (PR #283 병합 후)
- 위 SHA는 역사 기준점일 뿐이며, 다음 작업에서는 반드시 최신 main을 다시 조회해야 한다.

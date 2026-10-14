# Daily 06:00 Collection ↔ Instagram Accuracy Audit

매일 **06:00 KST**에 Main 자료수집 상태와 Instagram TCG Content 검증 상태를 함께 점검합니다.

## 비교 항목
- Main 핵심 수집 작업(release / market price / promo-event / FX)의 마지막 실행 시각
- 연속 실패, partial/recovered 상태, 반복 오류 signature
- source_collection_stats의 소스별 상태 기록 존재 여부
- Pokémon / ONE PIECE / NARUTO × KR/JP/US 3×3 커버리지
- 행사/프로모 링크 점검 신선도와 collection_errors
- Instagram source_routes의 fail-closed 정책과 소스 다양성
- 양쪽 runtime crosscheck snapshot이 존재할 경우 canonical_key 기준 사실값 agree/conflict

## SELFREFINE 안전 규칙
- Main/Instagram의 provider health, retry, learning/error state는 합치지 않습니다.
- 후보(candidate)를 상대 도메인의 verified 상태만 보고 자동 승격하지 않습니다.
- conflict 값을 평균하지 않습니다.
- 403/429 우회는 금지하고 Retry-After 및 승인된 대체 소스 전략만 사용합니다.
- 동일 underlying sale lineage는 독립 완료거래 증거로 중복 계산하지 않습니다.
- 보고서의 repair_actions는 검증된 수정 방향이며 문자열을 코드로 실행하지 않습니다.

## 스냅샷
사실값 비교는 각 도메인이 기존 exporter로 만든 런타임 파일을 사용합니다.

- Main: crosscheck_exchange/runtime-main.json
- Instagram: crosscheck_exchange/runtime-instagram.json

이 파일들은 의도적으로 Git에 커밋하지 않습니다. 한쪽 스냅샷이 없으면 06:00 결과는 snapshot_missing 경고를 남기며, 이를 성공한 사실 교차검증으로 간주하지 않습니다.

## GitHub Actions 시각
GitHub Actions cron은 UTC 기준이므로 workflow는 0 21 * * * 를 사용합니다.
대한민국은 DST가 없으므로 이는 매일 다음 날 **06:00 KST**입니다.

## 통합관리 계약
이 06:00 감사는 별도 시스템이 아니라 기존 `인스타 카드정보` 통합 TCG 관리체계의 하위 단계입니다. 새 채팅에서도 별도 TCG 자동화나 별도 감사 시스템을 만들지 않고 `TCG_INTEGRATED_MANAGEMENT.md` 계약을 기준으로 기존 시스템을 계속 업데이트합니다.

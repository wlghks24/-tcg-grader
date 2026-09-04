# SELFREFINE Collector Isolation

원칙: 같은 종류의 정보를 수집하더라도 취득 코드는 서로 다른 collector/provider로 유지한다.

- collector_id: 취득 코드 경로별 독립 ID. 오류/재시도/학습 이력을 공유하지 않는다.
- provider_id: eBay, PriceCharting, TCGdex 등 출처/공급자 계층 ID.
- information_family: market_price, completed_sale, promo_event, release_reprint, graded_photo, card_identity 등 같은 정보 종류를 묶는 논리 그룹.
- canonical_result_key: 카드/제품 identity가 동일한 결과끼리만 결과 계층에서 비교·중복제거 후보로 취급한다.
- lineage_key: collector_id + provider_id + canonical_result_key + source_locator 기반. 어느 취득 코드/출처에서 왔는지 끝까지 보존한다.

금지 사항:

1. 같은 정보를 모은다는 이유로 서로 다른 수집 코드의 오류 이력을 합치지 않는다.
2. 한 수집기의 403/429/timeout/parser 오류를 다른 수집기의 성공/실패 점수에 반영하지 않는다.
3. 서로 다른 카드 언어/variant/등급/통화를 같은 canonical 결과로 합치지 않는다.
4. 상충하는 가격을 평균내어 확정값으로 만들지 않는다. conflict 상태로 재검증한다.
5. 시장참고값/호가/리스팅을 실제 완료거래로 승격하지 않는다.

허용 사항:

- 여러 독립 수집기가 동일 identity의 같은 정보에 도달하면 결과 계층에서 교차검증 근거로 사용할 수 있다.
- 동일 information_family 내 결과는 canonical_result_key가 일치할 때만 비교한다.
- 최종 값이 같더라도 lineage_key는 각 collector/provider별로 별도 보존한다.

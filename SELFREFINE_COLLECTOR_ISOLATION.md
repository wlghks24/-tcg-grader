# SELFREFINE Collector Isolation

같은 종류의 정보를 수집하더라도 취득 코드는 서로 다른 collector/provider로 유지한다.

- `collector_id`: 취득 코드별 독립 ID. 오류/재시도/회귀 이력을 공유하지 않는다.
- `provider_id`: eBay, PriceCharting, TCGdex 등 원출처/공급자 ID.
- `information_family`: `market_price`, `completed_sale`, `promo_event`, `release_reprint`, `graded_photo`, `card_identity` 등 같은 정보 종류를 묶는 논리 그룹.
- `canonical_key`: 동일 카드/제품 identity 결과끼리만 결과 계층에서 비교하기 위한 키.
- `lineage_key`: collector + provider + canonical identity + source locator를 보존하는 출처 계보 키.

규칙:

1. 같은 정보를 모아도 수집 코드 자체는 합치지 않는다.
2. 한 수집기의 403/429/timeout/parser 오류가 다른 수집기의 retry_count나 학습 점수에 영향을 주지 않는다.
3. 같은 `information_family`라도 `canonical_key`가 일치할 때만 교차검증/중복제거 후보로 취급한다.
4. 결과 값이 같아도 각 수집기의 `lineage_key`는 유지한다.
5. 서로 다른 카드 언어/variant/등급/통화는 같은 canonical 결과로 합치지 않는다.
6. 상충 가격은 임의 평균하지 않고 conflict로 재검증한다.
7. `completed_sale`과 `market_price`는 다른 family로 유지해 실제 완료거래와 시장참고값을 섞지 않는다.
8. SELFREFINE `error_signature`에는 collector/provider identity를 포함한다.

# V669–V670 · 무료 공식 BOX + eBay 판매완료 관찰 + 검증 현황

2026-10-12 KST. GitHub PR #651 Draft/HOLD. 기존 30게임·338 사용자 미확인 후보·1,014 수동 조사 작업과 8개 링크/작업 보존. main 미병합.

## 제조사 확인: 일본 고질라 BP01 일반 부스터 BOX

- 제조사 공식 제품: https://godzilla-cardgame.com/products/bp01/
- 「ゴジラVSゴジラ」 일본판, **2025-07-05 출시, 1 BOX=12팩 × 1팩=7장**, 일본 BOX MSRP **JPY 5,280** (세금 포함).
- `tcg_official_product_supplement_v669.json`과 `tcg_official_overlay_v669.py`에서 제조사 URL·팩 수·가격·날짜·게임·국가·상품 ID를 정확하게 비교. 3-BOX 구매 증정 이벤트 ≠ 일반 부스터에서 무작위 봉입되는 HIT 확률.
- 제품 샘플 103→**104**, 일반 BOX 66→**67**, 공식 BOX ≥1개 확보 게임×국가 37→**38/55**, 공식 표본 공백 18→**17/55**. 전체 발매 BOX 전수확보를 뜻하지 않는다.
- WIXOSS US 역사판 공백 1곳 제외 시 활성 공백 **16곳**, 운영 목표 54개 활성 지역 중 49곳 확보까지 제조사 추가 지역 **11곳** 필요.

## 실거래 부족 부분의 실질적 개선: eBay Sold 표시 4건

미국판 **Pokémon Mega Evolution—Perfect Order** 밀봉 부스터 디스플레이(정확한 포장·판매자 표기 기준). 아래는 eBay 공개 원본 페이지가 `Sold`로 표시한 가격/날짜이다. **결제 정산, 반품/취소, 배송, 세금, 수수료는 확인되지 않았다.**

| 공개 eBay listing ID | Sold 표시 날짜 | 공개 화면 USD 금액 | 출처 |
|---|---|---:|---|
| 287489659057 | 2026-07-28 | $189.99 | https://www.ebay.com/itm/287489659057 |
| 206440921471 | 2026-08-01 | $159.99 | https://www.ebay.com/itm/206440921471 |
| 366663297662 | 2026-09-12 | $170.00 | https://www.ebay.com/itm/366663297662 |
| 336825478808 | 2026-10-03 | $169.99 | https://www.ebay.com/itm/336825478808 |

관찰한 단 **4건의 표시 가격 범위 $159.99–$189.99**, 단순 중간값 **$169.995**(사용자 표시 시 $170.00 반올림). 이는 표본 설명용 수치로, 시세 지수·현재 매수 가격·거래 정산 금액이 아니다.

`tcg_public_sold_listing_observations_v670.json` 및 `tcg_sold_listing_audit_v670.py`에서 listing ID/URL/상품명/날짜/표시 USD 금액을 고정 검증하고, `settlement_verified=false`, `delivery_verified=false`, `eligible_for_public_price_index=false` 를 강제. 출처/가격/정산상태 위조 시 차단. 판매 등록가·종료된 입찰·여러 품목 LOT·6팩 번들 및 36팩 디스플레이를 섞어 시세를 올리는 행위 금지.

### 출처 진실성 단계
1. `SELLER_ASKING_PRICE`: 판매 희망가, 실제 거래 아님.
2. `PUBLIC_SOLD_LISTING_OBSERVED`: 플랫폼 공개 페이지에 Sold/일자/표시 금액 표기 — **이번에 확보한 4건**.
3. `SETTLEMENT_VERIFIED`: 결제 정산과 취소·반품 여부까지 독립 검증 — **현재 확보 0건**.
4. `PUBLIC_PRICE_INDEX_ELIGIBLE`: 3단계에 배송비/세금·상품 동일성·날짜까지 검증한 자료만 허용 — **현재 0건**.

## 실행코드 연동과 검증 상태

- Python 30종 오프라인 수집 큐·출처감사, JavaScript 태블릿 공식 BOX·리서치·공백 레이더·30게임 카탈로그에서 위조 manufacturer data는 fail-closed 및 V668 이전 정상 103 샘플 보존.
- `test_tcg_v669_v670_box_sales.py`: 104상품/67 BOX/17공백, 4 Sold 목록/가짜 정산·가짜 URL·금액·PACK↔BOX 필터, 실제 Node.js 집계 대조.
- `tcg_free_preflight_v664.py --full`과 무료 GitHub Actions/CodeQL 검사에서 최신 commit의 Python·Node·보안 실행 결과를 별도 확인.
- **Lenovo 태블릿 실제 30분 자원/앱 렌더링/재부팅 테스트는 수행하지 않았음.** 시험은 기기에서 `python tcg_lenovo_termux_probe_v668.py --full --soak-seconds 1800`; 결과 JSON은 개인기기에만 저장, 자동 업로드하지 않음.
- 외부 사이트 크롤링 우회·유료 API·자동 결제 없음. eBay 공개 웹 페이지를 사람이 확인한 초기 증거 표본이며, 상업용 대량 수집 권한은 확보하지 않았다.

## 120점 재평가 / 승인 게이트

과거 V668 임시 **55/120**에서 공식 BOX 국가 한 곳 추가와 공개 Sold 자료 검증 경로가 개선되었다. **잠정 57/120**(BOX 19/30, 카드ID 7/20, 정산 검증 및 시세 1/20, 코어·CI 22/25, Lenovo 실측 0/15, 무료·안전 8/10 = 57). 자체 평가점수는 외부 기관 인증이나 정량화된 장치 성능지표가 아니다.

**남은 직접 과제:** 활성 제조사 BOX 국가 11곳 추가(현재 38/55), 카드번호 확보 게임 5→20+, 플랫폼 Sold 관찰 후 취소/정산의 독립 검증 및 금액 시간별 축적, Lenovo 실제 디바이스 관찰. CI 통과만으로 main 병합 금지.

**Release decision:** Draft/HOLD, main 미병합, 무료 조건 유지.

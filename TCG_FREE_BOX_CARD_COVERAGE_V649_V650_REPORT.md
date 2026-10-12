# V649–V650 · 무료 30게임 제조사 BOX/카드 원문 보강·취약 출처 차단·QA

**기준일:** 2026-10-12 (KST) · **GitHub PR #651 초안, main 미병합** · 유료 API/클라우드 필수 조건 없음.

## 사용자 요구 유지
- 30종 전체, 한국·일본·미국 90개 조사 범위, 기존 사용자 자료 338후보 (BOX/제품 198, 출시예정 42, HIT 60, 프로모 38) 손실 방지.
- 각 분류 내 중복 출처만 합침: 행사(EVENT)끼리, 프로모(PROMO)끼리, 콜라보(COLLAB)끼리, 영화(MOVIE)끼리. 분류 자체를 합치거나 경품·판매글/매입글을 실거래가로 승격하지 않음.
- 무료 공식 제조사 제품 사양 우선. 국가/판본별 팩수·출시일 다르면 데이터 분리. 제조사 사이트 매장 표시가≠MSRP≠실거래 가격.
- 네트워크 요청 폭주/403·429 우회 금지. **기본 조사 큐는 오프라인 0 HTTP**. 별도 공개 API는 기존 TCGdex/Scryfall 수동 --sync 선택시에만 사용.

## 실험으로 확인한 표본 범위

| 검증 지표 | V648 | V649 |
|---|---:|---:|
| 제조사 상품 샘플 수 | 76 | **88** |
| 30종 중 제조사 상품 표본 1건 이상 | 22 | **30/30** |
| `BOX` 제품 규격 샘플 수 | 42 | **51** |
| 등록 국가·게임 55조합 중 BOX 표본 확보 | 17 | **23** |
| 등록 국가·게임 55조합 중 BOX 규격 미수록 | 38 | **32** |
| 등록 국가·게임 55조합 중 공식 제품 표본 1건 이상 | 25 | **33** |
| 등록 국가·게임 55조합 중 공식 제품 표본 자체 미수록 | 30 | **22** |

**경고:** 30/30은 해당 게임이 최소한 1종류의 공식 상품 *예시*에 등장한다는 뜻일 뿐 제조사의 모든 SKU/세트/팩/출시일/카드번호/희귀도/가격을 수집했다는 뜻이 아니다. 32개 지역의 `BOX` 규격 공백과 카드별 완성도 공백은 여전히 크다. 원천 자체가 외부 사이트이므로 언제든 404/403/429 및 변경 가능.

## V649 제조사 공식 원문 근거 12건 (8게임)

| 게임·시장 | 제품 | 검증한 봉인규격 | 근거 | 주의 |
|---|---|---|---|---|
| Elestrals US | Base Set First Edition BOX | 36팩×10장 | https://www.shopelestrals.com/products/base-set-booster-box | 정확한 출시일 미확인 |
| Elestrals US | Moonrise First Edition BOX | 36팩×10장 | https://www.shopelestrals.com/products/moonrise-booster-box | 토퍼/시리얼 내용이 박스 당 보장이라는 뜻 아님 |
| UniVersus US | Godzilla: Reign of Kaiju BOX | 24팩×11장 | https://uvsgames.com/license/godzilla/ + https://uvsgames.com/learn-to-play/ | 출시 2026-03-13 |
| WIXOSS JP | WX26-P2 CONFLICT SELECTOR BOX | 14팩×8장 | https://www.takaratomy.co.jp/products/wixoss/product/wx26_p2/ + https://shop.yellowsubmarine.co.jp/products/detail/97538 | 2026-10-31 출시예정, 박스 규격은 타 유통사 교차검증 |
| CookieRun: Braverse US | Brave Beginning **팩** | 9장/팩 | https://cookierunbraverse.com/en/product/detail?id=211 | 발매 월 2025-07, 정확한 일자 미인증 |
| CookieRun: Braverse US | A Game of Truth and Deceit **팩** | 9장/팩 | https://cookierunbraverse.com/en/product/detail?id=241 | 2026-03-27; *아시아판 5장/팩·30팩/BOX를 영문판에 잘못 적용 금지* |
| Alpha Clash US | Echoes of Eternity BOX | 32팩×16장, 제조사 MSRP $119.99 | https://alphaclashtcg.com/news/can-you-hear-it-the-echoes-of-eternity-are-calling | 이전 세트는 24팩×10장일 수 있음. 다른 세트에 복사 금지 |
| Rush of Ikorr US | Shattered Chaos BOX | 24팩×9장 | https://upperdeckstore.com/rush-of-ikorr-tcg-shattered-chaos-booster-box.html | $89.99은 직영몰 표시가 |
| Rush of Ikorr US | Merciless Battlegrounds BOX | 24팩×9장 | https://upperdeckstore.com/rush-of-ikorr-tcg-merciless-battlegrounds-act-2-part-1-booster-box.html | URL·상품제목 Act 표기 충돌, 세부판본 식별 미확정 |
| MetaZoo US | Base Set BOX | 24팩, 팩당 장수 미확인 | https://www.metazootcg.com/shop | 직영몰 표시가는 MSRP 인증값 아님 |
| MetaZoo US | Nightfall BOX | 36팩, 팩당 장수 미확인 | https://www.metazootcg.com/shop | Base Set과 포장 규격 섞지 않음 |
| Cyberpunk TCG US | Kickstarter Beta 부스터 **팩** | 팩당 장수 미확인 | https://cyberpunktcg.com/marketing-materials + https://cyberpunktcg.com/faq | Beta와 일반 Retail 구분, Q3/Q4 배송 계획≠상품 출시 확정일 |

`tcg_official_product_supplement_v649.json`에 12건 등록. 미인증 세트코드는 `LOCAL-` 접두사와 `set_code_verified:false`, 정확한 출시일 미인증 시 `release_date_unverified:true` 표시.

## 실제 코드 보완

1. `execution/official_box_coverage_audit_v623.py`, `official_box_catalog_v626.js`의 제품별 공식 호스트 **제조사 도메인 allowlist** 확장.
2. `official_box_catalog_v626.js`, `tcg_30_game_catalog_v629.js`, `tcg_source_research_v634.js`, `tcg_source_audit_v633.py`에서 **V649 보강 파일을 이전 V637 뒤에만 추가**. 잘못된 메타데이터/누락 시 이전 제품 기록 유지. 이전 V637만 인수하는 JS/Python API는 계속 76 샘플 반환 (후방 호환).
3. **실제 오류 수정:** V649 출처를 조사 화면으로 전달할 때 URL 사칭 `shopelestrals.com.attacker.example`가 차단되지 않던 경로 발견. `tcg_source_research_v634.js`에 제조사 공식 도메인·국가·상품유형·BOX 수량·출시일 증거·금지된 시세 필드 검증 추가. 잘못된 V649 파일은 연구 UI 로딩 중 기존 V637 자료만 보존.
4. `tcg_multi_source_queue_v639.py`의 수동 조사 대기열도 새 자료 반영. 30종/3시장 1,014 수동 검색 작업은 삭제하지 않고 P0 BOX 공백에 우선 배치.
5. `test_tcg_official_coverage_v649.py`에서 88 제조사 제품/51 BOX/30게임·55등록시장 중 32 실제 BOX 공백, 338 원본 보존, 잘못된 제조사 URL·중복·판본·양방향 JS 회귀 검증 시나리오 **작성**.

## V650: 카드·HIT·프로모 원문 찾기

`tcg_manufacturer_card_discovery_v650.py`는 이미 저장된 **HIT 후보 60개+프로모 후보 38개를 KR/JP/US로 분리한 294개의 카드 검색 작업** 생성.

별도 공식 카드 DB 실제 주소가 확인된 예:
- WIXOSS 일본 https://www.takaratomy.co.jp/products/wixoss/card/card_list
- UniVersus 미국 https://uvsgames.com/universus/cards/
- Rush of Ikorr 미국 https://my.upperdeck.com/public/roi/cards
- Digimon 미국 https://world.digimoncard.com/cards/

다른 게임은 레지스트리 공식 제조사 사이트에서 Google/Bing을 통한 카드명 검색 **진입점만 제공**한다. 카드 공식번호, 판본, 병행 일러스트, 희귀도, PSA, 시세나 HIT 확률은 **기계적으로 추정하지 않는다**. 실제 카드 ID 검증을 마친 데이터가 이미 수집된 것처럼 말하지 않는다. `test_tcg_manufacturer_card_discovery_v650.py`는 294검색·4 공식 소스·무허가 호스트 거부를 테스트하도록 작성.

## 무료 앱/오픈소스 비교를 통한 개선 요소

- **TCGdex**: 다국어 세트 식별/로컬 캐시 → 지역·상품 규격별 출처 분리와 24시간 무료 캐시.
- **Scryfall**: 세트 카드수/인쇄 타입/벌크 데이터, 요청한도와 출처 정합 → HIT 확률 대신 검증된 카드 ID/인쇄판별 기록.
- **Pokecollector·CardVault**: 미개봉/카드/세트 목록 분리, CSV/JSON 내보내기와 미확인 후보 격리.
- **제조사 카드 갤러리**: 30게임 범위에 장기적으로 URL/버전별 출처를 우선 부착하는 방식. 카드별 제품 출시일/희귀도/HIT 확률은 각자 별도 증거 필요.
- **SNS/이벤트 발견 출처**: 행사끼리, 프로모끼리, 콜라보끼리 등 분류별 중복 통합한 기존 V648 유지. 키워드·검색엔진 발견 위치·원문 URL 모두 보존.

## 정량 목표 100+/120 — 인증 게이트

| 평가 항목 | 만점 | 현재 객관 근거와 남은 검사 |
|---|---:|---|
| 무료·30종 전체/원본 무손실 | 20 | 30/30 게임 상품 표본, 338 원본 후보 및 90 스코프 보존 |
| 정식 미개봉 BOX·팩/국가/버전 원문 증명 | 25 | 51 BOX 표본, 등록 국가 중 32 BOX 공백 남음 |
| 카드/HIT/프로모 개별번호/희귀도 검증 | 20 | 294 카드 검색 *계획* 신규, 개별 카드 완료인증 미달 |
| 실거래가/매입가/재고/출처 신뢰 | 15 | 수동 X/Google 조사 및 CSV 증거 스테이징, 실체결 검증 미완료 |
| 보안/404·403·429/재시도·오프라인 | 15 | 보안 경로 강화·JS 부분검증, 실제 사이트별 신뢰도/429 실측 미완료 |
| Python/Node 전체 회귀·CodeQL·무결성 | 15 | 테스트 작성, 최신 HEAD CI 통과 여부 별도 확인 필요 |
| Android Lenovo 장시간 UX·렉·재부팅 | 10 | 실기기 검증 필요 |
| **합계** | **120** | **100점+ 완료 인증은 전체 통과 근거가 있을 때만** |

GitHub PR #651은 승인/병합 준비 증거가 없으면 **draft/HOLD**. 업그레이드 시 사용자 유료서비스·GPU·유료 API 추가 불필요.

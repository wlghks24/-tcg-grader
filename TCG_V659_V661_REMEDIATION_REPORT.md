# V659–V661 무료 TCG 핵심문제 수정보완 · 제조사 BOX/카드번호/가격증거/수집 안정성

**기준:** 2026-10-12 KST, PR #651, main 미병합(HOLD). 유료 API/클라우드/구독/자동 결제 의존 0.

## 1. 제조사 BOX 공백 2지역 추가 축소 (V659)

두 제조사·공식 행사 원문에서 국가별 **일반 부스터 BOX와 낱팩** 구성을 확인.

| 게임/판본 | 정확한 근거 | BOX | 발매 | 주의 |
|---|---|---|---|---|
| Pokémon JP SV9a 『熱風のアリーナ』 | https://www.pokemon-card.com/products/sv/sv9a.html | 30팩 × 5장 | 2025-03-14 | **180엔은 낱팩 희망소매가**, BOX 정가 추정 금지. BOX 구매 증정 프로모는 봉입 HIT 확률 아님 |
| ONE PIECE JP OP-13 『受け継がれる意志』 | https://cp.onepiece-cardgame.com/festa/2025_summer/goods | 24팩 × 6장 | 2025-08-23 | 출시일 제조사 Bandai https://www.bandai.co.jp/catalog/item.php?jan_cd=4582769864865000 교차. 행사 BOX 판매가 5,280엔을 제조사 MSRP나 체결가로 착각 금지 |

파일 `tcg_official_product_supplement_v659.json`은 V657 부모 다음에만 추가되며, `tcg_official_overlay_v659.py`는 **제품 ID·이름·국가·세트코드·출시일·팩수·카드수·원문 URL 일치**와 중복/위조/유료 필드 차단. 제조사 한정 허용 호스트 `cp.onepiece-cardgame.com`만 추가(무제한 `*.onepiece-cardgame.com` 허용 안 함).

### 중복 없는 JSON 자료 재계산

| 항목 | V658 | V659 적용 시 |
|---|---:|---:|
| 저장된 공식 상품 샘플 | 94 | **96** |
| 일반 BOX 샘플 | 57 | **59** |
| 등록 게임×국가 지역 | 55 | **55** |
| BOX 표본 보유 지역 | 29 | **31** |
| BOX 표본 미수록 지역 | 26 | **24** |
| 30게임 시장×분류 조사 과제 | 540 | **540** |

Python 후보 수집 `tcg_multi_source_queue_v639.py`, 감사 `tcg_source_audit_v633.py`, 태블릿 공식 BOX 목록·30종 카드게임 UI·자료공백 레이더에 **V659 선택적 로딩/조건 검증**을 연결. 오염 V659은 V657까지의 정상 자료를 보존하도록 별도 fallback. V8 JS 모듈 로직 직접 실행에서 **96/59/24, V657 fallback 94, 악성 도메인 거부** PASS. 새 2건이 시장의 모든 BOX 또는 전체 제품 수집 완료를 의미하지 않는다.

## 2. 카드번호·HIT·프로모 오인 방지 (V660)

`tcg_manufacturer_card_evidence_v660.json`: 제조사 공식 카드 DB·행사 명단에서 직접 확인한 **카드번호 3건, 2게임** 초기 proof: Digimon US `BT25-001` Tokomon(C), `BT25-020` Marsmon(SR, 대체 아트), ONE PIECE JP `OP13-001` 몽키 D 루피(행사 참조; 희귀도 **미확인**).

- Digimon 공식 목록: https://world.digimoncard.com/cards/?category=522036&search=true
- ONE PIECE 일본 공식 참가 가능 카드: https://cp.onepiece-cardgame.com/flame-flame-fruit/side-event/event2

`tcg_card_trade_evidence_v660.py`: 카드번호뿐 아니라 **게임/국가/세트/인쇄 유형/출처/희귀도**를 일치시켜 다른 판본·이름 중복을 방지. 사용자 CSV에 매입 제시가 `STORE_BUY_OFFER`, 판매글 `SALE_LISTING`, **체결 주장** `COMPLETED_SALE_CLAIM`을 별도로 저장; 출처·날짜·통화·상태·RAW/PSA/BGS/CGC/TAG/BRG 등급 검사. 인쇄판·등급·지역이 다르면 동일 가격으로 합치지 않음. **완료 거래 주장도 증빙 없이 `verified_sale=false` 및 `eligible_for_public_price_index=false`.** 외부 URL은 다운로드하지 않으며 기본 네트워크 호출 0회. 인증 실거래/등급 가격 **0건 추가**.

## 3. 무료 개별 카드 데이터 목록 수집 확장 (V661)

`tcg_tcgdex_card_ids_v661.py`: 공개 TCGdex **세트 상세** `https://api.tcgdex.net/v2/{en|ja}/sets/{set-id}`에서 카드 번호·이름만 선택적 `--sync` (최대 1 GET), 24시간 캐시/ETag/304/429 중단/손상시 last-good 유지. 이미지, 가격, PSA, HIT 확률, 한국판 추정 사용하지 않음. 별도 표준라이브러리 기반 `test_tcg_tcgdex_card_ids_v661.py` 작성. 실제 외부 동기화 실측 이전에는 API 자료 수집 건수 0.

참고: https://tcgdex.dev/rest/set, https://tcgdex.dev/rest/sets. 커뮤니티 카드번호를 공식 제조사 인쇄판 증명으로 자동 승격하지 않는다.

## 4. 실행·보안·회귀 게이트

`test_tcg_v659_v660.py`에 96/59/24, V657 94 fallback, 제조사 호스트 위장, 이름·팩수·출시일 위조, 카드 ID/세트/판본 매칭, 통화 오류, 가짜 체결가/등급 혼동 테스트. `test_tcg_tcgdex_card_ids_v661.py`에 캐시 TTL, 429 유지, 대체 JSON 악성 입력, 중복 카드 번호, 네트워크 오류·리다이렉트 방어 테스트.

무료 GitHub Actions `.github/workflows/tcg-free-collector-qa.yml`을 확장하여 새 Python 파일 3종의 컴파일과 관련 unittest 추가.

```sh
python -m unittest -v test_tcg_v659_v660 test_tcg_tcgdex_card_ids_v661 test_tcg_v658_alignment test_tcg_collection_v641
python tcg_official_overlay_v659.py
python tcg_source_audit_v633.py --summary-only
python tcg_multi_source_queue_v639.py --format summary
python tcg_card_trade_evidence_v660.py --identity-summary
python tcg_tcgdex_card_ids_v661.py --lang en --set-id sv01
# 명시적 opt-in, 캐시 갱신 최대 1 GET:
python tcg_tcgdex_card_ids_v661.py --lang en --set-id sv01 --sync
```

**확인 완료:** GitHub 변경 파일·JSON 집계 및 V8 JavaScript 내부 함수 96/59/24, V659 누락 fallback 94, 부정 출처 차단. **확인 못함:** 실 Python 전체 테스트 실행 결과, 최신 HEAD GitHub Actions/CodeQL 성공 로그, 원격 공개 API 실접속, Lenovo 태블릿 Termux UI·장시간 메모리·재부팅 계측. 테스트 코드 존재≠실행 성공. PR Draft/HOLD & main 미병합 유지.

## 5. 100+/120 목표 달성 게이트

이전 V658 임시 근거점수는 **52/120**이었음. 이번 V659–V661의 신규 코드/자료를 포함한 설계평가(검증 완료 제품/소규모 카드 샘플 보상)는 **약 57/120 잠정**, 전체 제품 객관 품질점수는 **인증 보류**. 실제 전체 CI·CodeQL·태블릿 PASS 증거가 없는 영역은 합격 처리 안 함.

- 활동 지역 54곳 중 BOX 샘플 **49곳 이상**이 목표라면 현 31곳에서 **18곳 추가**. 단 1BOX/지역은 모든 발매제품 전수 수집이 아님.
- 30게임 중 최소 20게임의 공식 카드번호/희귀도/판본: 현재 2게임·3번호뿐이며 제조사/라이선스 있는 공개 데이터로 더 확보해야 함.
- 매입가·판매글·완료 거래를 실증증거/발생일·수수료·배송·환율 시점과 분리. 증빙 없는 완료 거래는 사용자 주장 단계.
- 최신 HEAD CI Python+Node 전체 검증, CodeQL, SHA256, 403/429 안전 복구 및 Lenovo 실기기 성능 테스트.
- 비용 및 법적 제한: 무료라는 단어는 LTE 데이터 요금 무료, API 상업용 재배포 허가, 영구 무제한 무료 사용을 보장하지 않음.

# V623 · TCG BOX / 팩 / HIT / 카드 자료 확보 및 결측 보고서

검토 기준: 2026-10-12 KST. 공식 상품 정보와 시장 호가·실거래는 **절대 같은 근거로 취급하지 않음**. 현재 데이터는 전체 시장 카탈로그가 아니라 독립 검증된 일부 상품의 로컬 스냅샷임.

## 1. 기존 자료 결함 — 정량화

| 구분 | 변경 전 | V623 후보 | 증명 범위 |
|---|---:|---:|---|
| 제조사 공식 BOX / 낱팩 / 프리릴리즈 상품 | 13 | 21 | 원문과 사양을 수동 대조한 항목만 |
| 공식 제품이 있는 게임 | 4 | 5 | Pokémon, ONE PIECE, GUNDAM, Digimon, Star Wars Unlimited |
| 등록 게임 | 30 | 30 | WATCH 포함. 새로운 게임 등급 기능 자동 승격 없음 |
| 선언된 KR/JP/US 게임·지역 조합 | 55 | 55 | 레지스트리에 선언된 지역만 |
| 이 목록에 공식 상품 1건 이상 있는 지역 조합 | 4 | 5 | 상품이 하나 존재한다는 뜻이며 **완전 수집 아님** |
| 공식 상품 항목이 0건인 선언 지역 조합 | 51 | 50 | 해당 조합에 상품이 없다는 의미 아님 |
| 검증된 단품 HIT 거래, 실거래 BOX, 개별 카드 전체 목록 | 입증 안 됨 | 입증 안 됨 | 이번 제조사 상품 스냅샷으로는 검증할 수 없음 |

**지역별 다섯 검증 셀:** Pokémon/KR 5 BOX, ONE PIECE/KR 4 BOX, GUNDAM/US 5 BOOSTER_PACK, Digimon/US 3 BOOSTER_PACK, Star Wars: Unlimited/US 2 BOOSTER_PACK + 2 PRERELEASE_BOX.

## 2. 이번 추가한 제조사 검증 자료

| 게임 / 지역 | 추가된 공식 제품 | 출시일 | 공식 BOX 또는 팩 사양 |
|---|---|---|---|
| Pokémon / KR | 30th CELEBRATION | 2026-09-16 | 20팩 × 6장, BOX 권장가 70,000원. 기념 피카츄 1장/팩 문구는 일반적인 확률형 HIT 보증과 구분 |
| Pokémon / KR | 스톰에메랄다 | 2026-08-21 | 30팩 × 5장, BOX 권장가 45,000원 |
| Pokémon / KR | 어비스아이 | 2026-06-26 | 30팩 × 5장, BOX 권장가 45,000원 |
| Pokémon / KR | 닌자스피너 | 2026-05-01 | 30팩 × 5장, BOX 권장가 30,000원 |
| Pokémon / KR | MEGA 드림 ex | 2026-01-23 | 10팩 × 10장, BOX 권장가 50,000원 |
| GUNDAM / US | Phantom Aria [GD04] | 2026-04-24 | 1팩 12+1장, MSRP $4.99. BOX당 팩 수 미확인 |
| GUNDAM / US | Eternal Nexus [EB01] | 2026-06-26 | 1팩 12장, MSRP $4.99. BOX당 팩 수 미확인 |
| Digimon / US | CHIVALROUS XIII [EX-13] | 2026-10-03 | 1팩 6장, 81종. BOX당 팩 수·시장가격 미확인 |

**검증 출처:** 
- https://pokemoncard.co.kr/card/960
- https://pokemoncard.co.kr/card/938
- https://pokemoncard.co.kr/card/907
- https://pokemoncard.co.kr/card/887
- https://pokemoncard.co.kr/card/859
- https://www.gundam-gcg.com/en/products/gd04.html
- https://www.gundam-gcg.com/en/products/eb01.html
- https://en.digimoncard.com/products/pack/ex-13/

공식 원문에는 판매가격과 팩 내용이 있지만, 중고 거래 체결가격·현재 매장 재고·시세 변동·풀레이트·등급 확률은 동일 문서에서 확인할 수 없다. 참고 이미지와 카드 일러스트는 저작권/사용권 확인 없이 복제하거나 공개 저장소에 수집하지 않는다.

## 3. 부족한 데이터의 종류별 보완 우선순위

**1순위 — 상품 실체/공식 카드 목록:** 원피스/포켓몬/나루토의 국가별 공식 BOX·팩·시리즈 세트코드·출시일·팩수·수록 카드·프로모 연결. 게임 공식 URL과 세트별 원문을 기록. 나루토 현재 공식 BOX 사양이 이 스냅샷에 없으므로 수치를 임의 보완 금지.

**2순위 — 판본별 HIT/고가 카드:** 공식 카드 목록에서 카드번호·레어리티·언어·일반/패러렐·삽화 차이를 구분한 후, 입증된 완료거래의 개별 거래ID와 링크를 수동 교차검증. 'HIT 확률'은 실측 표본·제조사 공식 고지가 없는 경우 미확인.

**3순위 — 한국/일본/미국 BOX 가격:** 제조사 정가, 판매자 호가, 체결가격을 별도 필드로 저장. 미개봉/개봉/재포장, 팩 수, 언어, 지역, 최신 확인일이 달라지면 다른 변형 상품 취급. 입출고/재고는 해당 점포의 명시적 확인 시각이 있을 때만 표시.

**4순위 — 사진/출시 세대/태블릿:** 상품 원문에 허용된 이미지의 이용권, 로컬 저장 여부, 촬영 결과 카드번호·세트 자동 제안 뒤 수동 선택. 실제 Lenovo 터치·네트워크·장시간 처리·업데이트는 기기 직접 검증 필요.

## 4. 무료로 유지하는 수집 경계

- 공식 제품 페이지와 자가 저장 JSON, Python 표준 라이브러리 검증은 추가 서비스 비용 0원. 외부 서비스 호출량/약관은 별도 적용.
- 포켓몬 공식 카드검색: https://pokemoncard.co.kr/cards
- 원피스 공식 한국 상품: https://onepiece-cardgame.kr/products.do
- 건담 미국 공식 상품: https://www.gundam-gcg.com/en/products/
- 디지몬 미국 공식 상품: https://en.digimoncard.com/products/
- 무료 TCGplayer 스캐너는 사람의 판본 검증 흐름 참고용. TCGplayer 판매 가격/카드 이미지를 허가 없이 대량 복제하지 않음.
- Pokémon TCG API / TCGdex / Scryfall 등의 공개 데이터는 각자의 API 이용 조건·호출 제한·게임 범위를 확인한 뒤 비상업적/유효한 사용 범위에서만 검토한다. 무료 API가 전 게임/전 국가를 지원한다고 가정하지 않음.

## 5. 자동 결측 검증 실행 (완전 로컬)

```bash
python -m unittest -v test_official_box_coverage_v623.py test_official_product_catalog_v599.py
python execution/official_box_coverage_audit_v623.py --output local_box_coverage_report.json
```

보고서는 30개 게임 × 3개 국가의 90개 셀을 작성하며, 선언된 55개 지역 조합과 비선언 35개 조합을 구분함. 공백 셀에는 수집 누락임을 표시하고, 실거래/HIT 확률/이미지 라이선스/실재고는 이 자료로 검증하지 않았음을 명시함. 보고서 생성 시 외부 접속·유료 API·파일 업로드는 하지 않음.

**100+20점 내부 목표:** 상품 데이터 21건 증가는 전체 수집이 끝났다는 근거가 아님. 현재 제품 완성도·실제 등급 정확도는 미채점이며, 시장·국가별 공백과 카드/HIT/실거래 근거가 해소되고 독립 검증이 끝나야 점수 부여 가능.

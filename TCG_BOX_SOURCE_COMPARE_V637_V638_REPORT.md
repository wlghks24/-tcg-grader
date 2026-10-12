# V637–V638: 30종 TCG BOX 자료 확충·실제 BOX 집계 분리·무료 비교 분석

작성일 2026-10-12 (KST) · PR #651 **draft, main 미배포** · 검증 전 병합 금지

## 데이터 보존과 정량 현황

- 기존 사용자 연구 입력 **30게임/30레코드** 유지: 제품·BOX·세트명 후보 **198**, 출시 예정 **42**, HIT 이름 **60**, 프로모 **38** (합계 338건의 **미검증 후보 항목**, 338개 서로 다른 카드를 뜻하지 않음).
- 제조사 공식 제품 증거 샘플: 기존 71 + 이번 V637 5 = **76건**, **22게임**.
- 그중 제품 유형이 정확히 `BOX`인 자료는 **42건**. `BOOSTER_PACK`과 `PRERELEASE_BOX`는 미개봉 일반 부스터 BOX 사양 증거로 계산하지 않는다.
- 공식 제품 샘플이 하나라도 있는 게임·국가 **25/55**, 없는 지역 **30/55**.
- **일반 부스터 BOX 사양 확보 게임·국가 17/55**, 일반 BOX 사양 미수록 **38/55**. 즉 8개 지역은 일반 팩이나 프리릴리즈 샘플만 보유. 예전 단순 `game_country_product_coverage_gaps` 값 30을 `BOX` 공백으로 오해하는 것은 정확도 오류.
- 등록 30종×3개 국가 검색 대상 90개를 유지, 제조사 발매국/언어판 선언되지 않은 **35개 조합은 단순 탐색용**.
- 남은 8게임은 현재까지 로컬 제조사 제품 스냅샷 0건: Cyberpunk TCG, Elestrals, Rush of Ikorr, CookieRun: Braverse TCG, UniVersus, Alpha Clash, MetaZoo, WIXOSS. **제품이 존재하지 않는다는 뜻이 아니며, 조사를 우선해야 함**.

## V637 새 공식 제품 5건

| 게임 | 국가 검색 기준 | 공식 BOX명 | 수량 | 발매일 상태 | MSRP |
|---|---|---|---|---|---|
| Riftbound | US 영문판 | Origins Booster Display | 24팩×14장 | ISO 정식 출시일 미확인 | 미인증 |
| Riftbound | US 영문판 | Unleashed Booster Display | 24팩×14장 | Riot Shop 배송 예정일과 발매일 구분 | 미인증 |
| Riftbound | US 영문판 | Radiance Booster Display | 24팩×14장 | 2026-10-23 스토어 배송 예상 시작, 출시일 미확인 | 미인증 |
| Grand Archive | US 대상 | Radiant Origins Booster Box | 24팩, 장수 미확인 | 2026-04-03 제조사 출시 공지 | 미인증 |
| Sorcery: Contested Realm | US 대상 | Arthurian Legends Booster Box | 24팩×15장 | 2024년 10월, 정확한 일자 미확인 | **$129 BOX MSRP** |

Riftbound 스토어 현재 판매/품절/가격 표시가 곧 제조사 **MSRP**나 체결시세라는 주장은 금지한다. Sorcery 제조사 공식 `MAP` $116.10은 `MSRP` $129와 다르므로 MSRP에 MAP을 대신 쓰지 않는다. 세트 코드가 확인되지 않으면 `LOCAL-` 접두사와 `set_code_verified:false`로 격리. HIT 확률/PSA 시세/보장 봉입은 추정 금지.

- Riot Origins: https://merch.riotgames.com/en-us/product/riftbound-origins-booster-display/
- Riot Unleashed: https://merch.riotgames.com/product/riftbound-unleashed-booster-display/
- Riot Radiance: https://merch.riotgames.com/en-us/product/riftbound-radiance-booster-display/
- Grand Archive RDO 릴리스: https://www.gatcg.com/article/radiant-origins-product-information
- Grand Archive 공식 박스팩수: https://www.gatcg.com/article/booster-boxes
- Sorcery 공식 상품: https://sorcerytcg.com/product/arthurian-legends?tab=product
- Sorcery 제조사 MSRP/MAP: https://sorcerytcg.com/map

## 시장의 무료 카드 데이터 서비스와 직접 비교한 설계 선택

| 서비스/기술 | 참고할 강점 | 무료 사용·정확성 제한 | 현 프로젝트 반영 |
|---|---|---|---|
| **TCGdex** | 포켓몬 세트/카드 식별·다국어 계층형 데이터 | 포켓몬 중심; 지원 언어·완전도, 이용조건 확인 필요 | 레지스트리/세트/판본을 분리하는 구조 참고, 다른 게임에 무단 확대 금지 |
| **Scryfall** | MTG 무료 카드 검색, 벌크 데이터, 점진적 갱신 | API 속도 제한·라이선스·대량 호출 관리 필요 | 오프라인 원본 보관 및 429 재시도 중지 원칙 |
| **JustTCG** | 상태/인쇄판본별 가격, 표본/이력, 불확실한 시세 상태 | Free **월 1,000/일 100/분 10건**, 20카드/호출 및 **개인 비상업용**; 키 필요. API 상업용 재배포·판매 조건 별도 | 가격 종류, 업데이트 시각, 현재값 만료를 반드시 구분. **프로젝트 필수 연동 금지**, 무단 수집/재배포 금지 |
| **제조사 공식 원문** | 출시일, 제품 구성, 원문 제품명, 판본 | 일부 상품 상세 404/502, 웹 색인 지연, 변경 가능 | 제조사별 허용 호스트, 원문→도메인·Google/Bing 대체 경로, 기존 검증 결과 보존 |
| **X 매입 공고 검색** | 한국/일본/미국 매장 buylist 탐색 | 판매 글과 혼합, 개인 계정·게시 날짜·판본 불명확, 로그인 제한 | 정밀/광역 검색 선택, 카드/BOX 분리, 제시 매입가≠실거래가격 |

JustTCG 정책 참고:
- https://justtcg.com/terms
- https://www.justtcg.com/docs/rate-limits
- https://www.justtcg.com/docs/api/cards
- https://www.justtcg.com/docs/changelog

## 실제 코드 반영

- `tcg_official_product_supplement_v637.json`에 제조사 BOX 사양 5건 추가 (원본 V599/V630/V636은 수정하지 않음).
- `execution/official_box_coverage_audit_v623.py`와 `official_box_catalog_v626.js`에 **Riot Store, Grand Archive, Sorcery** 제조사 도메인 allowlist; 회사 도메인 사칭 `sorcerytcg.com.evil.example` 거절.
- `official_box_catalog_v626.js`, `tcg_30_game_catalog_v629.js`, `tcg_source_research_v634.js`, `tcg_source_audit_v633.py` 모두 V637 추가 파일을 선택적으로 로드; 누락 시 이전 공식 자료 보존.
- `tcg_source_research_v634.js`는 **일반 BOX 샘플 42건/실제 BOX 공백 38곳**을 일반 상품 76건/일반 상품 공백 30곳과 명확히 분리 표시.
- `tcg_source_research_v634.html`에 **BOX 사양 미수록 우선** 필터 추가. 국가별 제조사 도메인에서 기존 198 BOX 후보를 Google/Bing로 검색하는 경로와 X KR/JP/US 검색을 유지.
- `tcg_source_audit_v633.py`에 `official_sealed_box_samples`, `declared_sealed_box_spec_gaps`, `sealed_box_records` 및 `sealed_box_status` 별도 출력.
- 새 `test_tcg_sealed_box_v638.py`에서 76/42/22/55/25/30/17/38과 338 사용자 후보 보존, 제조사 도메인 위장, URL 오류·빈 JSON·회귀검사, Python 및 Node 로직을 테스트 가능하게 작성.
- 과거 `test_tcg_source_resilience_v634.py`, `test_tcg_official_v636.py`의 고정 요약 데이터 테스트도 신규 BOX 카운터를 반영하도록 **역호환 업데이트**.

## 100+/120 목표와 승인 기준

| 배점 | 100+를 위한 **객관적 통과 근거** | 현재 검증상태 |
|---:|---|---|
| 20 | 기존 사용자 30종·338후보 무손실 보존 / 90국가 검색 | 저장자료·JS 로직 구조 확인 |
| 25 | 모든 게임·판본의 제조사 BOX·팩 사양·출시일 근거 | **42개 BOX 샘플 / 17지역**만 확보, 38지역 조사 필요 |
| 20 | 카드/HIT/프로모 번호별 정합성과 근거 출처 | 338개 저장 후보는 검증된 카드 목록이 아님 |
| 15 | KR/JP/US 매입/판매/체결 가격 종류 분리·출처 시각·상태 | X 검색 생성만 가능, 실매입가 검증 미완료 |
| 15 | 404/403/429/5xx 안전 대체경로, 출처 사칭 방지, 캐시 | 코드 및 부분 JS 검사. 실접속 안정성 실측 미완료 |
| 15 | 최신 HEAD 전체 Python/Node 테스트/CodeQL/무결성 통과 | 결과 미확인, HOLD |
| 10 | Lenovo 태블릿 실제 화면·렉·재부팅·오프라인 시험 | 미검증 |
| **120** | **최소 100 이상 실증 + 필수 승인 게이트 모두 통과** | **인증 점수 보류, 임의 100+ 금지** |

코드 스냅샷과 브라우저 테스트용 로직 검사 성공을 전체 GitHub CI 통과로 취급하지 않는다. Google/Bing/X/외부 제조사 페이지의 **404 영구 제로 보장은 불가능**하다. 403/429 차단 우회·무제한 재시도·유료 자동 전환 금지.

## 사용자가 직접 확인할 수 있는 무료 검사

```sh
python tcg_source_audit_v633.py --summary-only
python -m unittest -v test_tcg_sealed_box_v638.py test_tcg_official_v636.py test_tcg_source_resilience_v634.py
node --check official_box_catalog_v626.js
node --check tcg_source_research_v634.js
```

실제 검증 전에는 PR #651을 draft로 유지. 별도 유료 API, 클라우드, GPU 모델을 새로 추가하지 않음.

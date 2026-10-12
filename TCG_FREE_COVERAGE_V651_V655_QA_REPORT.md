# V655 무료 카드·BOX 자료 수집 QA 마무리 및 승인 보류 현황

기준: 2026-10-12 KST · GitHub `wlghks24/-tcg-grader` PR #651 (Draft) · 코드 입력/로컬 제품 표본 **완료도와 실제 전체 카드·BOX 데이터 완성도는 다른 지표**.

## 1. 직접 확인하고 반영한 최종 자료 현황

| 항목 | 현재 | 주의 |
|---|---:|---|
| 지원 카드게임 | 30/30 | 게임 이름/조사 대상 30개이지 각 게임 전 제품 수집 완료 아님 |
| 한/일/미 조사 범위 | 90 | 제조사가 해당 판본을 등록한 지역 조합 55 |
| 공식 제조사/직영몰 제품 **샘플** | **91건** | 출시일·팩 규격 등 원문 근거로 검증한 일부 제품 |
| 그중 실제 일반 BOX 샘플 | **54건** | 낱팩/프리릴리즈 BOX를 일반 BOX로 계산하지 않음 |
| 등록 국가별 BOX 규격 확보 | **26/55** | 범위 기준 47% |
| 등록 국가별 BOX 근거 미수록 | **29/55** | 존재하지 않는다는 증거 아님 |
| 영문판 운영 종료가 확인된 역사적 조사 범위 | **1곳** | WIXOSS 영문판 US; 과거 카드/중고 시장 조사 자체는 유지 |
| 현재 유통 신상품 BOX 조사 최우선(P0) | **28곳** | 29 공백 중 영문판 종료 1곳만 별도 역사 조사 |
| 기존 사용자 카드·BOX/HIT/프로모 후보 | **338개** | BOX/제품198·예정42·HIT60·프로모38 (미검증) |
| 수동 출처 검색 준비 작업 | **1,014개** | 상기 후보 × KR/JP/US, 결과나 실제 제품 1014개 아님 |
| 카드 HIT/프로모명 공식 검색 조사 | **294개** | 카드번호/희귀도/판본 확정 아님 |
| 제조사 제품·낱팩·카드·HIT·프로모·가격 공백 조사 | **540개** | 게임30 × 시장3 × 자료종류6, **오프라인 검색 작업 목록** |
| 행사/영화/콜라보/프로모 분류별 검색 범위 | **990개** | 게임30 × 시장3 × 행사분류11; 행사 실제 990건 아님 |

신규 V654 일본판 제조사 BOX 3건:
- 뱅가드 `VG-DZ-BT17` — **2026-10-09, 16팩/BOX×7장/팩**. 제조사 제품 색인 https://cf-vanguard.com/products/cat/booster/
- 디지몬 `BT-21 WORLD CONVERGENCE` — **2025-04-19, 24팩/BOX×6장/팩**. 일본 공식행사 https://digimoncard.com/event/2025/championship/items.php 와 세트 안내 https://digimoncard.com/products/pack/ver21/
- 유희왕 OCG `INFINITE FORBIDDEN` — **2024-04-27, 30팩/BOX×5장/팩**. Konami 유희왕 공지 https://yu-gi-oh.jp/news/oid-1859/
이 3건은 `tcg_official_product_supplement_v654.json`에 격리. 일본판 SKU를 한국판/영어판으로 자동 복사하지 않음.

## 2. 무료 카드 앱·오픈소스 비교로 실제 채택한 기능

- **TCGdex:** 포켓몬 EN/JA 공개 세트 색인만 필요 시 수동 동기화 `tcg_tcgdex_sets_v640.py --sync`. 이미지·BOX 보장·시세 필드로 확대 금지. 공식: https://tcgdex.dev/
- **Scryfall:** MTG 무료 세트 목록 `tcg_scryfall_sets_v643.py --sync`, API 제한/캐시·429 보수적 처리. `card_count`는 부스터 BOX 팩수가 아님. 공식: https://scryfall.com/docs/api
- **YGOPRODeck v7:** 유희왕 최신 무료 set index `tcg_ygoprodeck_sets_v651.py --sync`, 최대 한 번의 HTTPS GET(48h 캐시), 지난 API 가격 필드 제외/429 last-good 유지. 공개 문서: https://ygoprodeck.com/api-guide/
- **Pokecollector, CardVault, Open Source Trading Card Trackers:** 로컬 캐시, 수동 오프라인 백업, 미개봉 BOX와 카드판본/시장가격 증거 분리. 구조적 참고; 코드·이미지 및 판매용 데이터 재사용 권한을 뜻하지 않음.
- **공식 제조사 갤러리:** WIXOSS JP, UniVersus US, Rush of Ikorr US, Digimon US 카드 목록/번호 검색 링크를 `tcg_manufacturer_card_discovery_v650.py`와 `tcg_coverage_radar_v652.js`에 연결. 검색 결과만으로 카드번호·HIT 희귀도·실거래 자동 확정 금지.

기본 검색 큐/행사 증거·태블릿 표시는 추가 과금/로그인이 필요하지 않은 파일과 브라우저 링크 기반. 인터넷 연결에는 별도 통신 요금이 발생할 수 있으며 외부 무료 API 운영정책은 변경될 수 있음. **유료 API 신규 의존 0**.

## 3. 이번에 직접 수정한 코드 논리/보안 결함

1. `tcg_source_research_v634.js` — V654 일본판 정규식에서 백슬래시가 중복된 오류를 발견해 수정. JS 모듈을 V8에서 다시 실행: **91/91 제조사 상품 유효**, 54 BOX, 등록 55 중 공백 29.
2. `tcg_coverage_radar_v652.js/.html` — 태블릿에 540개 전체 중 첫 60개만 노출되고 이후 이동 못하던 문제를 **18개/페이지, 이전/다음, 필터 선택시 페이지 초기화**로 수정. 모의 DOM 렌더에서 91·54·29 및 페이지 이동·JP 필터 정합성 확인.
3. `tcg_coverage_radar_v652.js` — 일본 지역 검색에 영문 제조사 URL과 한국어 후보를 모두 AND 조건으로 강제하던 문제를 제조사 쿼리 영문/지역 쿼리 한국어·일본어로 분리. **검색 누락 완화**이며 실제 검색 성공률 보장 아님.
4. `tcg_30_game_catalog_v629.js/.html` — 원본 사용자 후보 표 화면에서 보강 JSON의 `game`·`id`만 믿고 공식 건수를 세던 문제 수정. 별도 유료 API 없이 같은 로컬 `official_box_catalog_v626.js` 제조사 화이트리스트·SKU 검증을 사용. V8 실제 실행: 정상 **91**, 사칭한 `yu-gi-oh.jp.attacker.example` **1건 거부해 90건** 인정.
5. `tcg_source_audit_v633.py` — 오프라인 보고서가 제품 행을 합산하기 전에 제조사 URL, 상품 종류, 지역·출시일·BOX 팩수 진위 검증을 호출하도록 수정. 판별기는 기존 `execution/official_box_coverage_audit_v623.py`를 재사용. 코드 작성 완료, 해당 Python 런타임 통과 여부는 GitHub Actions 또는 태블릿 Python 실행 증거가 필요.
6. `tcg_region_lifecycle_v653.json` — 영문 WIXOSS의 제조사 공지(2025-09-15) 기반 미국판 신규 발매 조사 우선순위 하향. JP 버전·과거 상품/미국 리셀 조사 데이터 삭제하지 않음. https://www.takaratomy.co.jp/products/en.wixoss/special/important_announcement.html
7. `.github/workflows/tcg-free-collector-qa.yml` — 외부 유료 API 요청 없이 Python 컴파일, **13개 collector/source/event 회귀 테스트 모듈**, Node 문법 검사 CI 가드 추가. `test_tcg_source_truth_v655.py`에서 공식 출처 위장/가짜 팩 유형/상위 목록 건수 거부 추가.

## 4. 100점/120점 이상 승인 게이트

| 심사 영역 | 목표 배점 | 승인 조건 |
|---|---:|---|
| 30게임·무료 실행과 자료 원본 무손실 | 20 | 원본 338후보/90시장 일치, API 키·유료종속 0 |
| 제조사 BOX/낱팩의 국가·판본·출시일/팩 구성 | 25 | **잔여 29게임×지역 BOX 공백 축소**, BOX/낱팩 혼동 0 |
| 실제 개별 카드·HIT·프로모 번호·희귀도 식별 | 20 | 검색 링크만 아닌 제조사 식별자/카드 결과 확보 |
| 매입/판매/실거래·시세 보존 | 15 | 거래 종류별 출처/확인시점, 의사 완료거래 가격 0 |
| 오류·렉·보안·403/429·오프라인 안전 | 15 | 429 시 중단/last-good/손상 보강자료 fail-closed |
| 전체 Python·Node·CodeQL·SHA256/PR QA | 15 | 해당 최신 **HEAD**에서 성공 증거 |
| Lenovo Termux 장시간 실행/재시작/UI | 10 | 실기기 측정과 재부팅 테스트 |
| **총점** | **120** | **실측 근거 없이 100점 이상 인증하지 않음** |

**현황:** 작업 브랜치 내용과 JS 부분 실행 결과를 확인했으나 실제 GitHub Actions/CodeQL/전체 Python 회귀와 Lenovo 실기기 증거가 부족하므로 PR #651은 **Draft / HOLD**, `main` 병합 보류. 모든 상품이 검증됐다는 주장이나 100/120 인증 점수 대신 객관적 잔여 조건을 기록.


## V656 무료 수집원 확대 — 기존 30종·1,014개 후보에 SNS/영상/식별자 조사 루트 추가

- 원본 사용자 입력 30종·338 후보, 지역별 1,014 검색 작업 및 공식 상품 91/BOX 54/미수록 게임·국가 29곳은 변경하거나 부풀리지 않음.
- `tcg_multi_source_queue_v639.py`: 기존 제조사 Google/Bing·시장 Google/Bing·X 5경로에 **공개 Instagram 게시물 Google 색인, YouTube 키워드 조사, JAN/UPC/상품번호 또는 카드번호 검색** 3경로를 더해 **각 작업 8개 무료 수동 검색 링크** 생성. 1,014건 기준 검색 *경로* 8,112개이며 실제 검증된 개별 자료 수는 0개 추가.
- 검색은 자동 수집·무단 크롤링·SNS API 대체가 아니라 사용자가 누를 수 있는 탐색 링크. Google에 색인되지 않은 Instagram 자료는 못 찾을 수 있고 YouTube 개봉 영상도 제조사 BOX SKU/봉입확률 증명이 아님.
- BOX/출시예정은 바코드(JAN/UPC) 식별어를, HIT/프로모는 카드번호·세트코드 식별어를 우선해 낱팩/BOX/동명이판 혼동을 줄이도록 검색 질의를 분리. 출처가 다르다고 독립적인 확인 3개로 계산하지 않음.
- CSV에도 3개 신규 경로를 내보내며 스프레드시트 수식 주입 보호 유지. Python 표준 라이브러리만 사용, 외부 유료 API/유료 구독/자동 결제/사용자 계정 권한 요청 없음. 기존 5개 키는 유지하는 추가형 변경.
- `test_tcg_collection_v641.py`에 8경로 전체 후보와 YouTube 쿼리 회귀 검사를 포함. 테스트는 CI 또는 로컬 Python 실행 시 검증되며 이번 업데이트에서 전체 CI·Lenovo 실기기 성공을 주장하지 않음.
- 참고: https://ygoprodeck.com/api-guide/ / https://tcgdex.dev/rest/sets / https://scryfall.com/docs/faqs/i-m-having-trouble-accessing-the-scryfall-api-or-i-m-blocked-17 / https://justtcg.com/terms. **상업 이용 제한 API를 기본 수집원으로 추가하지 않음**.

### 120점 승인 상태
검색 범위 확대는 수집 역량 개선이지만 공식 BOX 지역 공백 29개·확인된 카드 ID/실거래 자료 부족·최신 HEAD CI/실기기 미실측은 그대로. **100점 이상 실측 인증 보류, draft/HOLD 유지, main 병합 금지**.

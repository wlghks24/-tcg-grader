# V651–V654 — 무료 30종 TCG BOX/카드 수집 강화·실측 평가·승인 가이드

기준일 2026-10-12 KST · [PR #651](https://github.com/wlghks24/-tcg-grader/pull/651) Draft/HOLD · `main` 미병합.

## 검증 가능한 비교 사례 / 상업적 비용 경계

1. [PokéCollect](https://github.com/Trust1509/pokecollect) — 로컬 미러, 세트+카드번호 매칭, 불확실한 OCR 수동확인, 자료 누락 표시, 로컬 자료 소유권. 유료 Gemini Vision 연동은 **선택**이며 이 프로젝트에 붙이지 않음.
2. [Multi TCG Tracker](https://github.com/jbright471/Trading-Card-Collection-Tracker) — 출처 최신성·실패 기록, 카드 판본/언어/상태, CSV 미리보기, 원본을 덮어쓰지 않는 가져오기. 로컬 디렉터리 별도 보존 원칙 차용.
3. [Pokecollector](https://github.com/Git-Romer/pokecollector) — 각 언어판, 세트/카드 희귀도, 봉인 제품, 수동 등록 물품 분리. 제품 BOX 수량과 카드 수록 장수는 다른 계층.
4. [TCGdex](https://tcgdex.dev/) 포켓몬 EN/JA 세트, [Scryfall](https://scryfall.com/docs/api) MTG 세트, [YGOPRODeck v7](https://ygoprodeck.com/api-guide/) 유희왕 세트 **각각 무료 공개 API**에서 제한된 목록만 opt-in 수집. 사용료가 없다는 뜻이 이미지/IP나 상업 재판매까지 허용된다는 뜻은 아니며, 이미지/텍스트 대량 재배포 전 각 권리·이용조건 별도 확인.
5. **YGOPRODeck v7** 2026-09-03 변경으로 `tcgplayer_data` 필드 제거. 신규 수집기 `tcg_ygoprodeck_sets_v651.py`는 정확한 `https://db.ygoprodeck.com/api/v7/cardsets.php` 고정 주소의 세트명·코드·카드수·TCG 날짜만 취급. 다른 판본의 실제 BOX SKU, MSRP, 실거래가, HIT 확률은 저장하지 않음. 강한 무료/저부하 운영을 위해 **48시간 캐시, 수동 `--sync`, 최대 1 HTTP GET, 429 중지, 정상 캐시 보존**을 적용.
6. [Takara Tomy WIXOSS English 종료 공지](https://www.takaratomy.co.jp/products/en.wixoss/special/important_announcement.html) — 2025-09-15 영문판의 판매·개발 종료 발표. **WIXOSS 미국판은 역사 자료/중고 시장 조사 대상으로 유지**, 현재 신상품 BOX 우선검색에서는 제외, 일본 WIXOSS에는 적용하지 않음.

## 기존 30종 실제 자료의 발전

| 항목 | V648 | V650 | V654 |
|---|---:|---:|---:|
| 제조사 상품 예시가 있는 게임 | 22/30 | 30/30 | **30/30** |
| 누적 제조사 제품 자료 | 76 | 88 | **91** |
| 일반 `BOX` 자료 | 42 | 51 | **54** |
| 등록 국가·게임 55조합의 BOX 자료 확보 | 17 | 23 | **26** |
| BOX 자료가 없는 등록 국가 조합 | 38 | 32 | **29** |
| 제조사 제품 예시도 없는 등록 국가 조합 | 30 | 22 | **19** |

실제 카드 세트 전체와 인쇄판, HIT 종류별 희귀도, 세대, 매입·완료거래, 재고가 전부 수집됐다는 뜻이 아님. **원본 사용자 입력 338개 후보(제품 198+예정 42+HIT 60+프로모 38)는 삭제하지 않았다.**

### V654 제조사 일본어 BOX 실제 근거 3개

- **Cardfight!! Vanguard JP** `VG-DZ-BT17` 『運命星戦』: 일본 제조사 [상품 목록](https://cf-vanguard.com/products/cat/booster/), 출시 **2026-10-09**, **1BOX 16팩×7장**, 제조사 희망소매가 **6,160엔/BOX(세금 포함)**. 다른 카드파이트 제목 부스터 12팩·16팩과 혼동 금지.
- **Digimon Card Game JP** `BT-21` 『WORLD CONVERGENCE』: 공식 [제품 사양](https://digimoncard.com/products/pack/ver21/)에서 **2025-04-19, 6장/팩**, 반다이 주최 공식 [행사 물품](https://digimoncard.com/event/2025/championship/items.php)에서 **1BOX 24팩** 교차 확인. 대회 한정 지급/BOX 구입 특전은 일반 봉입 HIT 확률 아님.
- **Yu-Gi-Oh! OCG JP** 『INFINITE FORBIDDEN』: [유희왕 공식 발표](https://yu-gi-oh.jp/news/oid-1859/)에서 **2024-04-27**, **1BOX 30팩×5장**. 일본 OCG 상품이며 Rush Duel·영어판·미국 제품 포장 규격과 혼동 금지. 공식 제조사 세트 코드 직접 증명 없으므로 `LOCAL-` 임시 코드로 기록.

추가 자료는 `tcg_official_product_supplement_v654.json`에 이전 `v649` 다음으로만 연결. 이 파일이 없으면 **이전 88 상품·51 BOX 표본은 정상 유지**. `yu-gi-oh.jp`는 일본 KONAMI 공식 발표 도메인으로만 Yu-Gi-Oh 공식 출처 허용 목록 추가. 다른 게임에 이 도메인 재사용 금지.

## V652 자료 부족 현황판 — 검색 경로 확대 + 렉 방지

`tcg_coverage_radar_v652.html` + `tcg_coverage_radar_v652.js`:
- 30게임×3시장 **90칸**, 각 칸에서 BOX/낱팩/카드번호/HIT/프로모/가격증거 **6개 계층**으로 분리 → **540개 무료 조사 과제**. 이 수는 확인된 데이터/실거래의 갯수가 아니라 검색 과제.
- 제조사 검증 목록의 진짜 `BOX`만 BOX 자료로 집계. 프리릴리즈 세트와 `BOOSTER_PACK`만 있는 시장은 **BOX 공백 유지**.
- 55개 등록 시장 중 BOX 근거가 없는 **29곳** 표기. 영문 WIXOSS의 종료 증거를 제외한 **현재 출시 우선(P0) BOX 공백은 28곳**. **현재 출시 여부에 대한 다른 국가 전체의 실시간 인증은 아님**.
- 구체 공식 카드 리스트를 가진 WIXOSS JP, UniVersus US, Rush of Ikorr US, Digimon US는 `CARD/HIT/PROMO` 검색에서 해당 공식 카드 DB 우선 링크.
- 제조사 사이트가 영문인데 KR·JP 후보가 한글/일문인 경우 과잉 AND 검색으로 0건이 되는 오류를 수정. 제조사 사이트 검색은 제조사/게임/영문 타입을 우선, 일반 시장 검색에서 현지언어+후보로 재탐색.
- Lenovo에 맞춰 **18개/페이지**, 다음·이전 페이지와 게임/국가/자료 유형/빈 항목 필터. 검사에서 이전/다음·필터 초기화가 동작.
- 외부 API 0/유료 라이브러리 0. Google/Bing/X 링크는 **사용자가 눌렀을 때 검색**. WIXOSS 영문판 종료 자료는 증거 주석만, 원본 지역 레지스트리와 중고 자료 보존.
- `tcg_region_lifecycle_v653.json` — 제조사 공지 URL 기반 제품판 운영 상태 명시. 자료 자체의 실시간 재고/중고 거래중단을 뜻하지 않는다.

## V651 오프라인/무료 유희왕 세트 인덱스

`tcg_ygoprodeck_sets_v651.py`
- 기본 **오프라인 조회만** 함. `--sync`로 명시적 허용 후 하루 중 여러 번 실행해도 **48시간 캐시 유효한 동안 네트워크 0번**; 캐시 갱신은 단 1건 GET.
- YGOPRODeck v7 `cardsets.php`만 사용. 응답 크기 3MB, 세트 최대 5,000, 세트 코드/이름/날짜/카드수 검증·중복제거, ETag/304, 429/403 stop, HTTPS 리다이렉트 거부, 마지막 정상 자료 원자적 캐시.
- 검증하지 않은 이미지·시장가격·HIT/BOX 메타데이터는 제거. `num_of_cards`는 **세트에 존재하는 카드 수**이고 **봉인 BOX 안의 팩수나 카드수와 무관**.
- `test_tcg_ygoprodeck_sets_v651.py` — 미니 가짜 API 응답으로 304·429·캐시/파싱·오염 응답 복구 테스트를 작성. 실제 인터넷 실행 결과는 미인증.

## 검색 도구 테스트와 기존 자료 무결성

- `test_tcg_coverage_radar_v652.py`: 540 작업/30게임/90스코프/32 구형 BOX 공백/종료 시장 분리·출처 호스트 사칭 방어.
- `test_tcg_jp_manufacturer_box_v654.py`: 91 제품·54 BOX·29 공백/26 지역 커버/기존 v649 88·51 fallback/제조사 사칭 방어.
- `.github/workflows/tcg-free-collector-qa.yml`: GitHub 무료 Actions로 Python 표준 라이브러리 회귀와 Node syntax/JS 모듈 시험을 PR에서 수행하도록 **워크플로 파일 작성**. 작업 브랜치에 파일을 만들었다는 것과 실제 통과는 다르므로 *워크플로 실행/CI 승인 전 HOLD*.
- JS 제품 검증 및 30게임 gap radar 렌더링은 함수 실행 환경에서 실측해 **91/91 제품 스키마 검사, 54 일반 BOX, 26/55 지역, 29 지역 공백, WIXOSS 영문 제외 28 현재 우선 P0** 확인. 크로스 도메인 위조/잘못된 날짜 정규식 문제 발견 후 수정. Python/Android 실기기 QA 결과는 별도.

## 100점 이상을 받기 위한 구체 조건(총점 120, 객관적 게이트)

| 항목 | 최대 | 100점 목표를 위한 실측 목표 |
|---|---:|---|
| 무료·무과금 API/오프라인·자료 원본 보존 | 20 | 사용자 원본 338 후보·30게임·무료 핵심 앱 보존, 자동 유료 전환/전송 금지 |
| 제조사 상품/BOX 원문 완전성 | 25 | 등록 활동 국가 54곳 중 **최소 49곳의 진짜 BOX 규격 확보**(현재 26곳, 추가 23곳 필요). 부스터팩은 BOX로 계산 금지 |
| 카드·HIT·프로모 개별번호/판본·희귀도 | 20 | 30게임 중 최소 20게임에 근거 있는 카드 ID/세트 코드 기록, 한국/일본/영어판 혼합 금지 |
| 매입·판매·실거래 증거 구분 | 15 | 출처별 관찰일/통화/상태/수수료 분리, 무확인 가격 0 |
| 중복 행사 분류/출처 보존 | 10 | 행사끼리·프로모끼리·콜라보끼리·영화끼리 독립 통합, Google/Bing/공식 발견 링크 전부 원본 유지 |
| 보안·GitHub 전체 회귀·정상/404/429 복구 | 20 | HEAD CI·Node·Python·CodeQL 실제 통과, 제3자 악성 호스트/마이크로테스트·회귀 제로 실패 |
| Lenovo/Termux UI·메모리·재부팅 실기기 | 10 | 오프라인/온라인 전환, 이전/다음 전 페이지 순회, 메모리/렉·재시작 검증 |
| **총점** | **120** | **실증 증거 없는 단계는 임의 합격 처리하지 않음. 100+/120 인증 보류.** |

**운영 단축 명령:**
```sh
python tcg_multi_source_queue_v639.py --format summary
python tcg_ygoprodeck_sets_v651.py               # 네트워크 0
python tcg_ygoprodeck_sets_v651.py --sync        # 사용자가 동의한 뒤 최대 1 HTTPS GET
python tcg_source_audit_v633.py --summary-only
python -m unittest -v test_tcg_ygoprodeck_sets_v651 test_tcg_jp_manufacturer_box_v654 test_tcg_coverage_radar_v652
```

## 최종 안전 장치

모든 외부 연동은 해당 사이트 정책·상업적 이용조건, 저작권, LTE 데이터 비용 등을 개별적으로 따른다. 무료 REST API 접근 가능하다는 사실은 무제한 수집이나 판매 허가가 아니다. `main` 적용, CodeQL PASS, 100+/120 통과, 전체 실거래·재고 자동수집 완료는 현재 선언할 수 없다.

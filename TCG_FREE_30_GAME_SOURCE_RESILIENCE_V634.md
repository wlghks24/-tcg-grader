# V633–V634 무료 소스 정밀검증 / BOX 자료 확충 / HTTP 오류 대응

검토일 2026-10-12 KST · PR #651 draft · main 미반영

## 확인된 데이터 (기존 입력물 수정/삭제 없음)

- 30개 게임 ID, 30개의 사용자 입력 레코드 모두 보관: BOX·세트 후보 198, 출시예정 42, HIT 후보 60, 프로모 38.
- 별도 제조사 사양 **63개 부분 샘플** (기존 58 + V630 5), 샘플 존재 게임 **17/30**.
- 사용자 대상 국가 범위 55쌍 중 공식 제조사 제품 샘플이 하나라도 있는 범위 19쌍, **36쌍은 샘플 미수록**.
- 총 국가 검색 범위 30×3=90쌍; 35쌍은 레지스트리에 정식 출시 지역으로 등록되지 않았으므로 제품 미수록 오류가 아닌 **조사용(발매/언어 미확인)**.
- 이 숫자는 **카드 전체 체크리스트의 완성도/확인된 판매가격 수**가 아니다. 사용자 후보 제품 하나하나가 공식 63개와 1:1 검증 완료되었다는 주장도 금지.

## 웹 자료 비교 / 실제 발견

- 일부 제조사 상세 페이지는 자동 페이지 요청에 404를 반환하지만 제조사 상품 목록과 웹 색인에서 여전히 제품 스펙이 발견됨.
- Vanguard 원문 2개 주소: https://en.cf-vanguard.com/products/dz-bt14/ , https://en.cf-vanguard.com/products/dzbt16/ 는 자동 페이지 요청 404 응답이 관찰되었으나 https://en.cf-vanguard.com/products/ 의 색인 내용에는 제품명·발매일이 보임. 따라서 HTTP 404 한 차례는 단종/상품 미존재의 증명이 아님.
- Flesh and Blood https://legacy.fabtcg.com/en/articles/super-slam/ 은 자동 요청에 502이 관찰되었으나 최근 색인 사본 및 공식 상품 페이지에는 팩·BOX 판본 구성이 기재되어 있음. 원문 삭제는 금지하고 일시적 접근 오류로 재검토.
- FFTCG의 https://fftcg.square-enix-games.com/na/release/blissful-eternity 는 공식 18팩/BOX·12장/팩 자료가 접근 가능.
- TCGdex REST https://tcgdex.dev/rest 는 포켓몬 카드/세트 정보의 다국어 검색 모델 참고 (포켓몬 전용, 라이선스/재배포권 확인). Scryfall https://scryfall.com/docs/faqs/i-m-having-trouble-accessing-the-scryfall-api-or-i-m-blocked-17 는 과속 요청의 429와 대용량 조회 시 bulk 사용 권고.
- X 검색 및 매입 제시가 링크는 V631–V632에서 별도 제공. 로그인 또는 검색 제한, 자료 출처가 변할 수 있음. 유료 API나 우회 수집 금지.

## 이번 추가 구현

1. `tcg_source_routes_v633.js`: HTTPS 외부 원문 URL 검증, 게임별 제조사 공식 목록의 동일 사이트 계열 확인, 제조사 도메인별 검색 쿼리 생성, 404/410·403·429·502/503 상태 개별 분류.
2. `official_box_catalog_v626.js` + HTML: 상세 원문을 지우지 않고 **제조사 목록 및 도메인 검색 경로를 먼저 표시**, 상세 원문 404 가능성 알림. 레지스트리 로드 실패 시 기존 공식 63건 목록은 그대로 보임.
3. `tcg_source_research_v634.html` + JS: 30종 전체·90 국가 검색 범위, 공식 자료 미수록/부분 수록/정식 국가판 미확인의 3상태 필터, 198 BOX·제품명 후보별 제조사 검색, 태블릿 대응 페이지 이동. 42 출시예정/60 HIT/38 프로모 후보 보존 수량도 표시.
4. `tcg_source_audit_v633.py`: Python 표준 라이브러리 기반 로컬 30종 전수 조사 보고서. **기본 네트워크 호출 0건**. 선택적 `--probe`는 제조사 허용 URL 최대 6개만 HTTPS GET, 1.2초 간격, Range 지정·본문 미수집·자동 리다이렉트 금지, 429 즉시 중단, 인증 요구 403 우회 금지.
5. `test_tcg_source_resilience_v634.py`: 90/55/36/63/198+42+60+38 보존, 정식판 미확인 분리, HTTP 오류 유형, 악성 URL 거절, 검색 대체 경로 및 JavaScript 구문 확인용 검사 작성.

## 로컬 무료 실행 예 (네트워크 실행은 명시적 선택)

```sh
python tcg_source_audit_v633.py --summary-only
python tcg_source_audit_v633.py
python tcg_source_audit_v633.py --probe --probe-limit 4 --summary-only
python -m unittest -v test_tcg_source_resilience_v634.py
```

태블릿 새 화면(병합 후):
- `tcg_source_research_v634.html` 전체 BOX 출처 조사
- `official_box_catalog_v626.html` 제조사 공식 상품 샘플 + 원문 대체 경로
- `tcg_30_game_catalog_v629.html` 사용자 입력한 30종 전체
- `tcg_x_buylist_v632.html` X 일본/한국/미국 매입 제시가 검색

## 100+/120 목표 승인 항목과 남은 작업

| 목표 점수 | 게이트 | 현재 |
|--:|---|---|
| 20 | 사용자 30종 BOX/HIT/프로모 데이터 보존 | 레지스트리·입력 원본과 화면 구조 확인 |
| 20 | 30×3 국가별 공식 자료 조사·매입 검색 | 코드 추가 · 90 범위 계획 검토 |
| 20 | 제조사 상세 주소 404/403/429 오류 방어 | 분류·안전 대체 경로 및 제한된 수동 URL 검증 구현 |
| 20 | 제조사 BOX 상품·팩 수/발매/판본 정확도 | 17/30게임의 **63개 샘플**만 수록, 36 지역 샘플 공백 |
| 15 | 매입 제시가와 검증된 체결가 명확한 분리 | 검색 링크만 제공, 실제 매입가 수집 검증 없음 |
| 15 | Python·Node 전체 회귀·CodeQL·무결성 실제 통과 | CI/latest SHA 결과 확인 전 |
| 10 | Lenovo 실기기 화면·성능·중단/복구 시험 | 미검증 |
| **120** | **100점 이상은 각 게이트의 실증 완료 후** | **점수 미인증, PR HOLD** |

404를 전혀 만나지 않는 보장은 불가능하며, 근거 없이 다른 URL을 자동 공식 확정하거나 403/429 우회, 재시도 폭주, 유료 API 도입을 허용하지 않는다. 출처에 접근이 안 되어도 이전에 검증된 BOX 스펙과 사용자 입력 후보는 보존한다.

## 검토 참고 원문

- https://en.cf-vanguard.com/products/
- https://legacy.fabtcg.com/en/articles/super-slam/
- https://fftcg.square-enix-games.com/na/release/blissful-eternity
- https://tcgdex.dev/rest
- https://scryfall.com/docs/faqs/i-m-having-trouble-accessing-the-scryfall-api-or-i-m-blocked-17
- https://help.x.com/en/using-x/x-advanced-search


## 추가 V635: 중복 검색 경로·검색 누락 방지
- 제조사 도메인 `site:` 검색을 Google + Bing 두 경로로 제공. 검색 엔진 장애나 색인 누락 시 교차확인 수단으로 사용하되, 검색 결과만으로 BOX를 공식 데이터로 승격하지 않음.
- Microsoft Bing 연산자 참고: https://support.microsoft.com/en-us/bing/advanced-search-options
- 매장 게시물에 `買取`와 `販売`를 동시에 쓰는 경우 `-販売`로 정상 매입 공고가 빠질 수 있으므로 **정밀(제외어 유지)** / **넓게 검색(제외어 생략)** 2모드를 추가.
- Python: `python tcg_x_buylist_search_v631.py --game all --kind box --broad`; 또는 `generate_twitter_query("onepiece",region="JP",exclude_noise=False)`.
- 태블릿: `tcg_x_buylist_v632.html`에서 '넓게 검색' 선택 시 제외어 해제. 기존 정밀 검색 및 Python/JS 기본값 유지.
- `test_tcg_x_buylist_search_v631.py` · `test_tcg_x_buylist_v632.py`에 회귀 검사 추가. **동작 검증은 CI/실기기 확인 전까지 미인증**.

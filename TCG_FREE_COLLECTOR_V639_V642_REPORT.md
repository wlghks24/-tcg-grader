# V639–V642: 무료 30종 TCG 자료 수집 역량 확대 / 소스 증거 보전 / 안전 승인 게이트

작업 기준 2026-10-12 KST · PR #651 **draft/미병합**. 불법 크롤링, 유료 서비스 자동 가입·전환, 유료 API 필수 연결, 판본/가격 자동 확정 금지.

## 이번에 직접 비교한 실제 무료 프로젝트와 도입점

1. **Pokecollector** (https://github.com/Git-Romer/pokecollector): 언어별 TCGdex 카드/세트 캐싱, 이미지 누락, 봉인 제품·수동 제품을 분리. 참고: 게임/언어/제품 종류 분리, 로컬 last-good 보존.
2. **CardVault** (https://github.com/rhc52980/CardVault): sealed products/graded cards 별도 취급, CSV/JSON 내보내기 및 보유/미수집 목록 관리. 참고: 미검증 BOX 가격은 자동 생성하지 않음.
3. **Trading Card Collection Tracker** (https://github.com/jbright471/Trading-Card-Collection-Tracker): 백그라운드 재시도 간격, 로컬 캐시, 실패해도 마지막 확인 값 보존, CSV 불러오기·이상치 분류.
4. **Poke-TCG sealed matcher** (https://github.com/edobranchi/Poke-TCG-sealed-products-matcher): 동일 세트/상품 유형/판본만 교차매칭, 애매한 결과는 승인 대기. 이름만 비슷한 영어/일본어판 카드나 1st/Unlimited, 낱팩/BOX 시세 합산 금지.
5. **TCGdex** (https://tcgdex.dev/rest/sets): `https://api.tcgdex.net/v2/en/sets`, `/ja/sets`에서 무료 세트 ID/이름/수록 카드 수를 검색. **커뮤니티 세트 목록이지 제조사 BOX 포장 사양·HIT 확률·한국판·실거래 확정 근거가 아님**. 원본 이미지 저작권·소스 약관과 별개. API 키 없음, 정해진 강제 쿼터가 없더라도 24시간 캐시와 429 중지를 사용.
6. **기존 Pokémon TCG API** (https://docs.pokemontcg.io/): 공식 문서상 2027-03-01 서비스 종료 예정. 신규 필수 연동하지 않고 유지보수 가능한 TCGdex 검토.

## 저장된 실데이터에 기반한 30게임 수집 실측

- 레지스트리 **30게임**, KR/JP/US 90개 조사 범위 (등록된 지역 55, 미등록 탐색 35).
- `tcg_user_research_intake_v625.json`: 원본 30레코드, BOX/세트 후보 198, 출시예정 42, HIT 60, 프로모 38 = **338 후보**.
- 게임/분류 내 후보 텍스트 정규화 중복 0건 (이후 스크랩/타 언어 동일상품 중복이 없다는 뜻은 아님).
- 338후보×3개 시장 = **1,014개 수집 작업**. 30종 전체에 대해 제품 594, 예정 126, HIT 180, 프로모 114개 작업. 모두 **USER_SUBMITTED_UNVERIFIED** 및 제조사/판매/체결가 미확인.
- 제조사 스냅샷 **76개 상품 샘플** 중 실제 `BOX` **42건**, 공식 BOX 사양 지역 17/55, BOX 조사 우선순위 공백 **38/55**. 30게임 중 일부만 공식 근거가 있으므로 1,014개 작업 수를 제품 완성도/상품 수로 쓰면 안 됨.

## 실제 코드

### 1. V639 30게임·90시장 다중 출처 큐

`tcg_multi_source_queue_v639.py` — **무료, 기본 오프라인/네트워크 0건**, Python 표준 라이브러리.

- 30게임 × 3시장 × 4종 (BOX·제품, 예정, HIT, 프로모) 1,014개 조사 작업. Unicode NFKC와 공백/대소문자 정규화, 안정적인 SHA256 task_id, 게임·언어·시장 유지.
- 각 항목별 **제조사 Google/Bing**, 일반 시장 Google, 검색어 보강 Bing, X 최신 검색 **5개 링크**. 개별 출처를 읽어온 것이 아니라 사람의 조사 접근 경로임.
- 시장별 공식 BOX 누락 **P0**, 등록 지역 부분 샘플 **P1**, 해당 지역 공식판 미선언 **P2**. 404 상세 URL 대신 제조사 원문이 있는 국가의 사이트 도메인을 우선 검색. 공식판 없는 국가에 출처를 억지로 추가하지 않음.
- CSV/JSON/JSONL 내보내기, `--game`/`--region`/`--kind`/`--limit`. 셀 수 제한/검색어 인젝션 방어/CSV 수식 인젝션 방어.
- 생성 작업에 `manufacturer_approved:false`, `price_kind:"NONE"`, `PENDING_HUMAN_SOURCE_VERIFICATION` 고정. 일치하는 이름이 있다고 승인 금지.

### 2. V640 포켓몬 공개 세트 자동 수집 (명시적 opt-in)

`tcg_tcgdex_sets_v640.py` — `python tcg_tcgdex_sets_v640.py` 기본은 **오프라인 캐시 상태 출력**만 함.

- `python tcg_tcgdex_sets_v640.py --sync`를 사용자가 명시해야 **영어/일본어 세트 목록 최대 2 HTTPS GET**.
- 24시간 로컬 캐시 TTL, ETag/If-Modified-Since, 자동 리다이렉트 거절, 1.5MB 응답 크기 제한, 세트 ID/이름/개수 형식/중복 검증, 임시 파일을 이용한 원자적 교체.
- 404/403/429/5xx/타임아웃/잘못된 JSON에서 기존 캐시 보존. 403·429 확인 시 나머지 언어 수집도 중지. 재시도 폭주/유료 API/이미지 재호스팅 없음.
- 캐시 자료는 `COMMUNITY_POKEMON_SET_INDEX`; 제조사 정식 BOX, 팩수, MSRP, HIT, 한국판 데이터로 **승격 금지**.
- 태블릿 단독 Termux/Python 3 운영 가능. 기본 캐시 경로 `~/.tcg_grader/tcgdex_sets/`. 실제 태블릿 인터넷 동작 미실측.

### 3. V641 태블릿 수집 UI 확대 및 회귀 테스트

`tcg_source_research_v634.js`: 기존 BOX 제품 후보 검색을 **출시예정, HIT, 프로모 후보까지 확대**, 후보 각각에 공식 제조사 Google/Bing, 시장 Google, X 검색 링크를 노출. 브라우저에는 외부 API 키나 추가 패키지가 없으며 `textContent`로 안전 렌더링. JSON/링크는 로컬 준비 후에만 사용됨.

`test_tcg_collection_v641.py`는 1,014개 큐 중복/게임/분류별 5개 링크·무료 조건·검색어 인젝션, TCGdex 24h/304/429/403/캐시 손상 복구·리다이렉트 차단과 URL 안전 테스트를 위해 작성.

### 4. V642 외부 자료 CSV 수집·검증 준비

`tcg_source_staging_v642.py` — **사용자가 별도로 확보한 링크/자료를 CSV로 합칠 때**:
- `task_id,source_url,source_type,observed_at,amount,currency` 컬럼 요구.
- `manufacturer/store_buy_offer/sale_listing/completed_sale/community_index` 유형과 KRW·JPY·USD **시장별 통화**, 출처 HTTPS, 날짜·금액·중복 검사.
- 공식 제조사 도메인을 다른 사이트가 모방해도 허위 공식 인증 금지, 출처 내용 자동 다운로드 금지.
- 합격 항목도 **승인 대기**. `is_completed_sale_verified:false`, `is_official_product_verified:false`. 반려 원인과 수량을 기록, 다른 폴더에 새 JSON을 원자적으로 내보내며 기존 30게임 카탈로그를 절대 덮어쓰지 않음.
- `test_tcg_source_staging_v642.py` 회귀 테스트 작성.

## 실행 예 (표준 라이브러리 / 추가 유료 서비스 없음)

```bash
# 현재 파일이 모두 있는 저장소 폴더에서:
python tcg_multi_source_queue_v639.py
python tcg_multi_source_queue_v639.py --game pokemon --region JP --kind BOX_SET --limit 30 --format json
python tcg_multi_source_queue_v639.py --format csv --output ./export/tcg_research_1014.csv
python tcg_tcgdex_sets_v640.py                 # 오프라인 캐시 상태
python tcg_tcgdex_sets_v640.py --sync          # 수동 동의 시 EN/JA 최대 2회 GET
# 실제 출처 관찰값/URL을 승인하지 않은 CSV로 저장한 다음:
python tcg_source_staging_v642.py --input ./export/my_sources.csv --output ./export/staged_unverified.json
python -m unittest -v test_tcg_collection_v641.py test_tcg_source_staging_v642.py
```

CSV 예시 헤더:
```csv
task_id,source_url,source_type,observed_at,amount,currency
```

실제 `task_id`는 V639 CSV/JSON 출력에서 복사. 제조사 상품 원문, 매장 buylist 제시가, 광고용 판매가, 체결가를 혼합하지 말 것.

## 100+/120 승인 근거

| 영역 | 최대 | 원칙 |
|---|---:|---|
| 30종/90시장/원본 338후보 데이터 보존 | 20 | 1,014 조사 작업 중복 검사 + 소실 0 |
| 공식 BOX·팩·세트/실물 판본 포괄성 | 25 | 현 76개 샘플, 42개 BOX / 38개 실제 BOX 지역 공백 추가확보 필요 |
| 공개 카드/세트 데이터 수집 신뢰성·복구 | 15 | TCGdex 오프라인 캐시/24h TTL/304/429/교차 언어 및 수집실험 |
| 카드·HIT·프로모 실제 식별/연관 검증 | 15 | 후보 검색과 카드번호 확인을 구분, 아직 대량 검증 미완료 |
| 매입/판매/실거래/지역판 가격 출처 분리 | 15 | 스테이징 격리, 제시가≠실거래가 |
| 최신 HEAD CI/보안/QA·무결성 실측 | 20 | GitHub Actions·Python·Node·CodeQL 통과 근거 필요 |
| Lenovo 실기기/오프라인/재시작 테스트 | 10 | 앱·Termux 실제 사용자 단말 검증 필요 |
| **합계** | **120** | **실제 객관적 검증이 끝나기 전 100+ 인증은 보류** |

> API 호출에 비용이 발생하지 않더라도 통신사 LTE 데이터 요금·외부 운영사의 미래 정책 변경·상업적 재배포 라이선스는 별도 문제다. 공개 무료 앱의 사양을 복사하는 것이 아닌, 정당한 데이터 계층·정확성·복구 설계만 참고한다.

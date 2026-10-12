# TCG Grader V663–V664 · 정밀 감사 / 무료 BOX + 프로모·CI 사전검사

**기준:** 2026-10-12 KST, PR #651 feature branch; `main` 미병합. 사용자 원본 30게임 338개 후보 및 국가별 조사작업 1,014개 유지.

## 실제로 확인된 결함·공백 및 수정

| 발견/리스크 | 수정 또는 보호 |
|---|---|
| Pokémon **US** 공식 일반 BOX 표본이 없는데 일본어판으로 대체하면 판본 오류 | Pokemon.com 미국 공지(2026-03-13)로 Mega Evolution—Perfect Order **36 booster packs × (10 game cards + 1 Basic Energy)**, 미국판 일반 Booster Display 2026-03-27 발매를 별도 기록 |
| 같은 확장팩의 Elite Trainer Box 9/11팩, Build & Battle Box 4팩+고정 덱을 일반 display BOX로 세는 오류 | V663은 정확한 `product_type=BOX`, `packs_per_box=36`, `cards_per_pack="10"` 지정. 기본 에너지는 별도, BOX MSRP·상점 재고·실거래 및 HIT 확률 미확인 |
| 구매 프로모 카드 Gengar/Luxray/Aurorus를 봉입 HIT 또는 일반 세트 카드번호로 추정할 위험 | 제조사 2026-03-13 공지의 미국판 유통처 행사 이름 3건을 별도 `tcg_official_promo_evidence_v663.json`에 보존. 미국 GameStop Gengar, Best Buy Luxray, Hot Topic/Barnes & Noble Aurorus. US$15 이상 구매 시 재고 한정 제공; 번호 3개 모두 **미확인 / null** |
| 잘못된 새 자료가 이전 99개 공식 상품을 가리는 문제 | `tcg_official_overlay_v663.py`, `official_box_catalog_v626.js` 등에서 제품 ID·제조사 출처·날짜·36팩·10장·프로모 행사 스키마를 별도로 검증. 오류 시 새 단계 차단, 이전 정상 99건 유지 |
| 숫자만 늘리고 Windows/태블릿에서 검사하지 못하는 문제 | **`tcg_free_preflight_v664.py`** 표준라이브러리 기반 동일 운영 진단: 핵심 SHA-256, 원본 30종·338후보/1,014 조사작업, 공식 BOX 표본, 확인 카드번호·프로모 구분, 미확인 데이터 승격 방지 |
| 태블릿 공식 BOX 화면에서 순차적인 보강 JSON 요청으로 지연 가능 | `official_box_catalog_v626.js`에서 로컬 보강 9개 파일+프로모 증거를 **병렬 프리페치**하고, 실제 검증은 V630→V663으로 순서대로 진행하도록 수정. V8 모의 화면 테스트에서 9+1 요청 시작 및 기존 정상 1건 보존을 확인. 이 성과는 응답속도 실기기 밀리초 측정이 아님 |
| GitHub Actions 자동실행 기록이 없어 완료 여부가 보이지 않는 문제 | 무료 Actions workflow에 v663/v664 컴파일, v663 Python/JS 회귀검사, `python tcg_free_preflight_v664.py` 검사 추가. 단 아직 **최신 HEAD CI 실행 기록/CodeQL 완료 증거 없음** |

## 검증된 공식 자료

- [Pokémon USA: Mega Evolution—Perfect Order Product Showcase](https://www.pokemon.com/us/news/pokemon-tcg-mega-evolution-perfect-order-product-showcase) — 미국 일반 디스플레이 BOX 36팩, 10장+기본 에너지/팩, 2026-03-27 발매.
- [Pokémon USA: Perfect Order Purchase Promotions](https://www.pokemon.com/us/news/celebrate-pokemon-tcg-mega-evolution-perfect-order-with-promo-cards) — 2026-03-27 시작, 미국 카드명/판매처/15달러 이상 구매 조건, while supplies last.
- [Bandai UNION ARENA 2023 specifications changes](https://www.unionarena-tcg.com/en/news/003.php) 및 [2024 revision](https://www.unionarena-tcg.com/en/news/009.php) — 상품·시기에 따라 20/16/12팩 BOX 달라짐. **모든 제품에 동일 BOX팩수 적용 금지**. 해당 공식 문서들이 제품 단위 BOX 증거로 자동 변환되거나 실제 HIT 확률로 추정되지 않도록 별도 보관.

### 추가 V664 보안·UI 개선

- 신규 제조사 BOX와 프로모 증거에 허용되지 않은 임의 필드(`unverified_price_guess`, `surprise_hit_odds` 등)가 섞이면 **Python과 JavaScript 양쪽 검증기에서 실패**하도록 화이트리스트 적용. 팩 개수 Python 자료형도 정수로 엄격 확인.
- 태블릿 조사 화면 `tcg_source_research_v634.js`은 Pokémon 미국 지역을 열었을 때만 3개의 **제조사 확인 구매 행사 프로모 이름**을 별도 목록으로 표시. 원본 미검증 HIT·프로모 후보 338개와 합산하지 않고 카드번호 미확인/구매조건/재고한정을 표시한다.
- 공식 BOX 화면은 제조사 보강 JSON 9개와 프로모 자료 1개를 병렬 요청한 후 판본별 검증순서는 보존한다. **V8의 모의 DOM·네트워크 테스트**에서 파일 10개 동시 시작, 630단계 요청이 완료되지 않아도 나머지 9개 요청 시작, 404가 나더라도 기본 공식 자료 1건을 유지함을 확인했다. 실제 Android 성능 개선(ms) 또는 렉 제거는 실기기 미실측.
- `test_tcg_v663_pokemon_us.py`에 위조 가격/프로모 확률, Node 화면 9+1 요청/기존 자료 보존 회귀 시나리오를 추가하고 테스트 스크립트 JavaScript 구문을 별도로 검사했다. 이는 CI 실행 결과가 아니다.

## 교차검증 결과

V8 JavaScript 실제 저장소 파일에 GitHub 저장된 JSON 데이터를 주입해 재실행한 결과:

| 결과 | V662 | V663 |
|---|---:|---:|
| 제조사 공식 제품 표본 | 99 | **100** |
| 일반 부스터 디스플레이 BOX 표본 | 62 | **63** |
| 등록 지역쌍 | 55 | 55 |
| 지역당 최소 1개 BOX 제조사 근거 존재 | 34 | **35** |
| 최소 BOX 표본 없는 지역 | 21 | **20** |
| 30게임 × 3국가 × 6조사 항목 | 540 | **540** |
| 원본 조사 후보로 생성한 수동 검색 작업 | 1,014 | **1,014** |
| 구매 프로모 이름 확인 (별도, 미승격) | 0 | **3** |
| 구매 프로모 카드 고유번호 입증 | 0 | **0** |
| 신뢰 가능한 실제 완료거래 가격 신규 수집 | 0 | **0** |

V8 점검에서 정상 V662 99 fallback, 잘못된 미국 BOX 팩수, 위조 행사 카드번호 거부 확인. 이 점검은 **전체 Node/Python CI 실행/태블릿 설치 검증을 대체하지 않는다**.

## 재현 가능한 무료 로컬 진단

프로젝트 파일이 있는 디렉터리에서:

```sh
python tcg_free_preflight_v664.py
python tcg_free_preflight_v664.py --full
```

`--full`은 추가 외부 요청 없이 6개 표준라이브러리 unittest를 실행하며 환경에 Node.js가 설치돼 있으면 별도 JS 통합 테스트도 수행함. 결과 JSON에서 `PASS`, `FAIL`, `REVIEW`를 구분한다. FAIL이면 배포·병합 거부. PASS여도 최신 GitHub Actions/CodeQL·Lenovo 실기기 증거 없이는 `HOLD_PENDING_EXTERNAL_PROOFS`; **자동 배포/병합 없음**.

`CI` 워크플로는 GitHub의 해당 PR/커밋에 연계된 실행 목록과 상태를 조회했으나 이번 턴에 성공 기록을 얻지 못함. GitHub UI > Actions에서 workflow 활성/실행 가능 여부, 제한량, workflow 파일이 현재 브랜치에 있는지, PR checks 및 로그를 확인해야 한다. 수동 `workflow_dispatch`는 워크플로가 기본 브랜치에 있어야 검색·실행 가능한 플랫폼 제약이 있으므로, 아직 `main`에 병합되지 않은 파일은 현재 브랜치의 `push`/PR 이벤트만 사용한다.

## 점수 (120점 목표, 객관적 승인 여부)

**현재 100/120 인증 불가.** 과거 57/120 평가는 잠정적 설계평가일 뿐, 실측·정량 성능점수로 확정할 수 없다. 이번 작업은 공식 BOX 근거 지역을 34/55→35/55로 개선하였으나, 이는 '지역별 최소 한 BOX 표본 유무'이지 전체 세트 전수율이 아니다.

남은 주요 게이트:
1. *진행중인 54개 지역* 중 최소 49개 BOX 표본 목표: 현재 35곳 표본, WIXOSS US 역사판 제외된 경우 **추가 14곳**. 단 각 출시 BOX 전수 기록·재고·시세는 별도.
2. 공식 카드번호·판본·희귀도 확정 게임: 현재 **2게임/3카드 표본**. 공식 또는 정당한 이용권의 자료로 20게임 이상 검증하기 전 정확도 주장 금지.
3. 매입 제시가/판매등록가/실제 체결가·배송·수수료·환율 시간표 분리: 이번에 새로 검증한 완료거래 **0건**.
4. 최신 HEAD Python/Node 통합 CI·CodeQL, SHA-256 전수/핵심파일, Lenovo Tablet(Termux) 오프라인·메모리·설치 실기기 테스트 결과 필수.
5. 외부 유료 API/무단 스크래핑/403-429 우회/자동 과금 금지, 무료 API의 상업용 이용권 및 정책 별도 확인.

**Release decision: HOLD, PR draft 유지, main 병합 금지.**

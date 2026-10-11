# V636 — 무료 30종 공식 BOX 확장 및 제조사 원문 대체 경로 실측

작성일: 2026-10-12 (KST) / PR #651 작업 브랜치. **main 배포 완료 아님**.

## 확인된 결과 / 30게임 입력원본 보존

- `tcg_game_registry.json` 및 `tcg_user_research_intake_v625.json` 입력 30/30 유지.
- 사용자 입력 제품·BOX·세트명 후보 198개, 출시예정 42개, HIT 이름 60개, 프로모 이름 38개는 `USER_SUBMITTED_UNVERIFIED` 상태 유지.
- 제조사 공식 상품 샘플: V599 58 + V630 5 + V636 8 = **71개**, **19게임**. 실제 30게임 **전종 BOX 전체 목록**이 아니며 공식 샘플이 게임당 한 건 있는 것을 완료로 착각하지 않는다.
- 등록 게임-지역 범위 55중 공식 샘플 존재 **22개**, 샘플 미수록 **33개**. 30×3=90개 검색범위 중 정식 등록 외 35개는 탐색만 수행.

## 이번에 제조사 자료를 직접 대조한 BOX 여덟 건

| 카드게임 | 인쇄 국가 | BOX | 팩/BOX | 카드/팩 | 정가/BOX | 출시 |
|---|---|---|---:|---:|---:|---|
| hololive OCG | JP | ボリュームヴォルテックス | 12 | 8 | ¥5,280 | 2026-09-19 |
| hololive OCG | JP | サマー・ホログラム (EX) | 8 | 10 | ¥5,280 | 2026-08-21 |
| hololive OCG | JP | グローリー・エコー | 12 | 8 | ¥5,280 | 2026-12-18 예정 |
| Shadowverse: Evolve | JP | Academy Royale / アカデミー・ロワイヤル | 12 | 8 | ¥5,280 | 2026-07-31 |
| Shadowverse: Evolve | JP | Over the Calamity | 12 | 8 | ¥5,280 | 2026-10-02 |
| Shadowverse: Evolve | US(영문판) | New World Genesis | 12 | 8 | 미확인 | 2026-03-27 |
| Shadowverse: Evolve | US(영문판) | Convergent Destinies | 12 | 8 | 미확인 | 2026-05-22 |
| Shadowverse: Evolve | US(영문판) | Neometropolis | 12 | 8 | 미확인 | 2026-07-24 |

각 항목은 `tcg_official_product_supplement_v636.json`에 별도 스냅샷으로 기록. 공식 상품의 임의 임시 세트코드는 `LOCAL-`과 `set_code_verified:false`로 구분. 영문판 미국 제품 페이지가 404를 반환하는 환경이 있으므로 **검색 캐시/제조사 목록 확인과 라이브 상태 확인을 혼동하지 않음**. 유료 API·유료 모델·유료 클라우드·사용자 계정 등록을 요구하지 않는다.

제조사 출처:
- https://hololive-official-cardgame.com/products/post/volume-vortex/
- https://hololive-official-cardgame.com/products/post/summer-hologram/
- https://hololive-official-cardgame.com/products_detail/glory-echo/
- https://shadowverse-evolve.com/products/bp21/
- https://shadowverse-evolve.com/products/bp22/
- https://en.shadowverse-evolve.com/products/bp16/
- https://en.shadowverse-evolve.com/products/bp17/
- https://en.shadowverse-evolve.com/products/bp18/

## 404 대응 결함 수정

- 기존 V633의 출처 대체 경로 검사에서 **20개 제품**은 게임의 기본 제조사 URL과 실제 한국/일본판 제조사 도메인이 다르다는 이유로 제조사 목록 링크를 놓쳤음.
- `tcg_source_routes_v633.js`: 원문 URL은 게임별 제조사 allowlist를 통과했다는 전제하에, 기본 등록 출처와 국가별 도메인이 다르면 해당 **원문 제조사 호스트의 HTTPS 홈**을 대체 경로로 표시. 404가 일어나지 않는다는 보장과 혼동하지 않는다.
- `tcg_source_research_v634.js`: 원문이 있는 국가 셀은 레지스트리 일반 사이트보다 **그 국가에서 공식 샘플로 보관한 제조사 출처**를 먼저 사용해 198개 이름 후보의 검색 경로를 생성.
- `official_box_catalog_v626.js`, `tcg_30_game_catalog_v629.js`, `tcg_source_research_v634.js`, `tcg_source_audit_v633.py`: V636 보강 자료를 분리 로드/표시. 누락·오류가 있으면 이전 공식 스냅샷을 보존하고 일부 보강 자료 로드 실패 경고 표시.
- `test_tcg_official_v636.py`: 30종 원본 보존, 71 공식 제품, 22/55 공식 지역 샘플 존재, 33 공백, PACK/BOX·국가/언어·제조사 도메인 검증, Python/Node 병렬 조건, 71개의 대체 경로 검증을 위한 테스트 추가.

## 적용 가능한 무료 공개 기술 참고

- **TCGdex** https://tcgdex.dev/fr/faq : 포켓몬 카드/세트 다국어 API, 계정·API 키 불필요. **한국어는 2026-10 기준 지원 예정**이므로 일본어·영어를 자동으로 한국판이라고 표시하면 안 됨. 무료라도 같은 엔드포인트의 대량 반복 다운로드는 로컬 캐시 사용.
- **Scryfall** https://scryfall.com/docs/faqs/i-m-having-trouble-accessing-the-scryfall-api-or-i-m-blocked-17 : MTG는 대량 조회 시 bulk 이용, 429 발생 시 무작정 재시도 금지. 무료 API 가용성은 운영 정책에 따름.
- 제품 링크/제조사 검색/Google·Bing 조사 URL은 **출처 검증 후보**이지 그 자체로 제품 공식 승인 증거가 아님.

## 120점 목표: 실측 증거 기준

- 25점: 사용자 입력 30/30 데이터 유실 없이 검색·국가별 조회
- 20점: 카드/BOX·HIT·프로모 검색 90개 범위, 일본어/한국어/영어·넓게/정밀 모드
- 25점: 제조사 공식 각 세트 제품의 발매일·BOX 구성·판본·정가/근거검증
- 15점: 원문 404/403/429/5xx 대응, 제조사·검색 출처 다중 검증, 크롤링 정책 준수
- 15점: 최신 HEAD Python/Node 전체 회귀·CodeQL·manifest 무결성
- 10점: Lenovo 태블릿 실제 로드·렉·접근성
- 10점: 매입 제시가/체결가/BOX MSRP 혼합 방지, 무료 조건 유지
- **100+/120 승인 게이트**: 공식 자료 전수에 가까운 커버리지 + 모든 필수 품질 검사 및 실기기 테스트 통과 전에는 점수 인증 불가.
- 최신 PR #651은 **draft, main 미병합**. 저장소 HEAD Actions/Lenovo 실제 통합 검증 전 승인 금지.

권장 로컬 검사:
```sh
python -m unittest -v test_tcg_official_v636.py test_tcg_source_resilience_v634.py test_tcg_x_buylist_search_v631.py test_tcg_x_buylist_v632.py
python tcg_source_audit_v633.py --summary-only
node --check official_box_catalog_v626.js
node --check tcg_source_research_v634.js
```

시장 실거래 가격, 개봉 HIT 봉입률, PSA 인증 성능을 별도 자료 없이 추정/발행하지 않는다.

# V658 TCG Grader 무료 BOX 자료·수집 UI·QA 교차검증

기준: 2026-10-12 KST | 대상: PR #651, `feat/v628-official-sealed-proof-20261012` | Draft / main 미병합

## 근거 재확인 (제조사 직접 원문)
1. Lorcana Shimmering Skies: [Ravensburger](https://www.disneylorcana.com/en-US/product/shimmering-skies) — 하비 2024-08-09, 일반판매 2024-08-23, 24팩/BOX, 12장/팩.
2. Digimon EX-12 Digital World Shambala: [Bandai](https://world.digimoncard.com/products/pack/ex-12/) — 2026-07-03, 24팩/BOX, 12장/팩. 미국 $4.99는 **낱팩 MSRP**, BOX 정가가 아니다.
3. Star Wars Unlimited Spark of Rebellion: [FFG BOX 구성](https://starwarsunlimited.com/articles/sparking-rebellion)과 [2024-03-08 출시](https://starwarsunlimited.com/products/set-1-spark-of-rebellion) — 24팩/BOX, 16장/팩.

이 3건만으로 해당 게임 미국판의 모든 BOX, 라이선스, 카드별 HIT 확률, 재고, 매입·체결시세를 검증한 것으로 주장하지 않는다.

## 실제 발견한 결함과 변경

| 결함 | 해결 |
|---|---|
| 이전 V657 증거 파일을 BOX/30게임/자료공백 화면에서 불러오지 않아 숫자가 91/54로 남는 문제 | `official_box_catalog_v626.js`, `tcg_30_game_catalog_v629.js`, `tcg_source_research_v634.js`, `tcg_coverage_radar_v652.js` 간 신규 US 3건 연결. 태블릿 조사 HTML에 공식 validator 스크립트 순서 추가 |
| V656 Python 8검색 경로가 태블릿 UI에서 4경로만 보이는 문제 | Instagram 색인/YouTube/식별번호 검색 링크 추가, 기존 링크와 구분. 모두 수동 조사 전용 |
| V657 JSON에 공식 도메인만 맞는 거짓 BOX 추가 위험 | 정확히 3개 제품ID/게임/미국판/24팩/12·16장/출시일/세트코드 고정 확인, 원본·출시 원문 호스트/금지 가격/중복 ID 검사 |
| V654 부모 보강이 손상되어도 V657을 붙일 위험 | 신규 BOX UI에서 부모 전체의 기존 product validator 통과 필수. 실패 시 V657 제외·기존 정상 목록 표시 |
| Python 조사 작업과 출처감사 합계가 구형 91건으로 남는 문제 | `tcg_multi_source_queue_v639.py`와 `tcg_source_audit_v633.py`에 선택적 V657 누적 및 오염자료 차단. 존재하지 않으면 구형 자료 보존 |
| 테스트 미연결 및 잘못된 SHA 증거 | `test_tcg_v658_alignment.py` 교차언어 회귀/악성 데이터/원본 무손실/무결성 검사, GitHub Actions Python+Node 검사 목록 추가, 해당 브랜치 push 검증 경로 |

## 저장소 데이터 실제 JS 로직 재실행 결과

브라우저 프레임워크 없이 V8에서 기존 JavaScript 파일을 로드하고 정상 JSON 30게임·338후보·제조사 보강을 주입해 확인했다.

| 데이터 레이어 | V657 미포함 (기존) | V657 포함 (신규) |
|---|---:|---:|
| 공식 제조사 제품 표본 | 91 | 94 |
| 진짜 일반 BOX 표본 | 54 | 57 |
| 등록 게임×국가 범위 | 55 | 55 |
| BOX 표본이 있는 범위 | 26 | 29 |
| BOX 표본 없는 범위 | 29 | 26 |
| 전수 조사 분야별 작업 | 540 | 540 |

기존 표본 91개 fallback, 로카나 제조사 호스트 위장 및 카드장수 조작 시 추가 데이터 차단 확인. V656 Python 검색 경로는 기존 1,014작업×8링크이며 실제 수집 완료 건수 **아님**.

**실행 증거 경계:** 이번 대화에서 V8 JavaScript 직접 호출 기반 로직 검사는 통과했다. 그러나 실제 Python/Node 전체 unittest 런, 최신 GitHub Actions 실행 로그, CodeQL, Lenovo 실물 태블릿·재부팅·장시간 렉/메모리 검사는 통과 증거 없음. 프로그램 전체 100+/120 인증은 HOLD.

## 실측 증거 기반 임시 품질 채점 (120점 만점)

이 채점은 전체 앱의 성능 추정치가 아니라 **이번 데이터수집 요구조건에 대한 확인된 근거 수준** 평가이다. 미실측 항목은 점수를 주지 않으며, 향후 CI/현물 출처/실기기 검사 완료 시 재채점.

| 평가 기준 | 만점 | 잠정점수 | 근거/누락 |
|---|---:|---:|---|
| 30게임·원본 338후보·무료 운영 | 20 | 20 | 로컬 30·338 자료와 무유료 코드 구조 |
| 제조사 BOX 제품별 지역 검증 | 25 | 13 | 55 공식 지역쌍 중 29쌍에 BOX 표본; 상품 전수 아님 |
| HIT·프로모 개별카드 번호 정합 | 20 | 2 | 후보 조사만 가능, 대량 카드번호 검증 미완료 |
| 매입·판매·체결가격 근거 | 15 | 4 | 자료 유형 격리 구조는 있음, 인증된 실거래 부족 |
| 행사·프로모 분류 및 출처 합치기 | 10 | 5 | 로컬 로직 일부 검사, 실전 전수 미확인 |
| 보안·코드·회귀·CI | 20 | 8 | V8 로직·위조 출처 일부 확인, HEAD CI/CodeQL PASS 미확인 |
| Lenovo Termux 실기기·오프라인/성능 | 10 | 0 | 실제 사용자 장비 로그 없음 |
| **합계** | **120** | **52/120 (잠정)** | **100+/120 출시 승인 조건 미충족** |

## 100+/120 향후 필수 조건

- 공식 활동 지역 54개 중 BOX 증거 지역 최소 49: 현재 V657 포함 29곳이므로 적어도 20곳 추가. 단 '지역당 1제품' 목표도 전체 BOX 데이터 완결을 뜻하지 않음.
- 30게임 중 20게임 이상 카드번호, 세트 코드, 공식 희귀도와 판본을 제조사/적법한 공개 데이터로 교차 검증.
- 국가별 매입 제시가, 판매등록가, 실제 완료 거래가를 결제·수수료·관세/배송·환율 시점과 구분해 시차 및 실패 상태 기록.
- 최신 HEAD Python 전체 회귀, Node 테스트, CodeQL, 파일 무결성, Lenovo 실기기 재시작·오프라인·메모리·응답성 확인.
- 무료·적법한 출처만 사용, 비상업 한정 API 필수 의존 금지, 외부 사이트 403/429 우회 금지, paid API/automatic upgrade 불가.

### 실행 명령
```sh
python -m unittest -v test_tcg_official_overlay_v657 test_tcg_v658_alignment test_tcg_collection_v641 test_tcg_source_truth_v655
python tcg_official_overlay_v657.py --summary-only
python tcg_source_audit_v633.py --summary-only
python tcg_multi_source_queue_v639.py --format summary
node --check official_box_catalog_v626.js
node --check tcg_source_research_v634.js
node --check tcg_coverage_radar_v652.js
node --check tcg_30_game_catalog_v629.js
```

**HOLD:** 데이터 근거·검증·CI 확인 전 main에 합치거나 Lenovo에 '완전검증' 패키지로 배포하지 않음.

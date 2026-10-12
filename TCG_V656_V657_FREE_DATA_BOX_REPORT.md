# V656–V657 무료 TCG 수집·BOX 증거 개선 및 승인 보류 보고서
작성일: 2026-10-12 (KST) · 대상 PR #651 draft · main 미병합

## 적용 사항
1. 기존 30게임 338개 미검증 이름후보 × KR/JP/US = 1,014개 조사 작업과 5개 수동 검색링크를 보존.
2. V656에서 조사 항목마다 공개 Instagram 검색엔진 색인, YouTube 검색, BOX 바코드(JAN/UPC) 또는 카드번호·세트코드 검색을 추가해 **8경로 × 1,014 = 8,112개의 검색 포인터** 제공. 이는 수집 실적이 아니다. 유료 API·SNS 자동 스크래핑·유료 계정·자동 결제 없음.
3. V657에서 제조사 웹 원문에 직접 나타나는 봉인 BOX 3제품의 24팩 구성과 카드장수·출시일 확보. 입력용 `tcg_official_product_supplement_v657.json`은 **별도 승인대기 오버레이**라 기존 main/태블릿 UI의 공식 91건·BOX 54건을 자동 변경하지 않는다.
4. 오프라인 `tcg_official_overlay_v657.py` 및 `test_tcg_official_overlay_v657.py` 추가. 공식 도메인 위장/출시일 2차 URL 위조/중복 ID/BOX 수량/가짜 시장가격/추가파일 체인 공격을 차단하며, 이전 등록 자료에 새 출처만 추가할 때 지역별 BOX 공백이 줄어드는지 점검한다.
5. 무료 GitHub Actions 수집 QA 워크플로의 Python 컴파일 및 unittest 대상에 신규 오버레이·테스트 추가. 관련 SHA-256 및 UTF-8 bytes `integrity_manifest.json` 갱신.

## 제조사 공식 검증 링크

| 게임 | 시장 | 일반 BOX | 팩당 카드수 | 출시일(기준) | 공식 근거 |
|---|---|---:|---:|---|---|
| Disney Lorcana Shimmering Skies | US | 24 | 12 | 2024-08-23 일반 유통(하비샵 08-09) | https://www.disneylorcana.com/en-US/product/shimmering-skies |
| Digimon DIGITAL WORLD SHAMBALA EX-12 | US | 24 | 12 | 2026-07-03 | https://world.digimoncard.com/products/pack/ex-12/ |
| Star Wars: Unlimited Spark of Rebellion | US | 24 | 16 | 2024-03-08 | https://starwarsunlimited.com/articles/sparking-rebellion ; https://starwarsunlimited.com/products/set-1-spark-of-rebellion |

상품 제조사 SKU 인증이 없는 제품은 `LOCAL-`와 `set_code_verified:false` 사용. 제조사 페이지의 `$4.99` 낱팩 MSRP를 BOX MSRP로 승격하지 않는다. 포장 사양만으로 HIT 확률·판매 가격·실재고를 만들지 않는다.

## 저장소 증거 합산 비교 (가설 아닌 로컬 레지스트리·JSON 집계)

| 대상 | V655 기존 합계 | V657 증거 파일을 포함한 독립 합산 |
|---|---:|---:|
| 공식 제조사 상품 샘플 | 91 | 94 |
| 실제 BOX 유형 샘플 | 54 | 57 |
| 정식 등록 게임×국가 지역 범위 | 55 | 55 |
| 일반 BOX 표본 보유 지역 | 26 | 29 |
| BOX 표본 미수록 지역 | 29 | 26 |

신규 확보된 지역: **Disney Lorcana US / Digimon US / Star Wars: Unlimited US**. 이 수치는 모든 BOX 제품 포괄률이 아니며 단일 표본이 있어도 그 지역의 다른 제품은 미수록일 수 있다. JSON 교차 계산 검사만 실행하였고 **Python 전체 unittest·CI·CodeQL·Lenovo Termux 실기기 통과 증거는 아직 없다**. PR draft/HOLD, main 미병합 상태를 유지한다.

## 100+/120 심사 게이트 — 실측되지 않은 점수 임의 부여 금지

| 분야 | 최대 | 실제 인증 조건 |
|---|---:|---|
| 30종·338후보 원본 무손실, 무료 운영 | 20 | 30/30·338/338·90지역 보존, 유료 서비스 종속 0 |
| 제조사 일반 BOX 국가·판본·팩수/출시일 | 25 | 활동 지역 54곳 기준 최소 49곳의 *실물 일반 BOX* 공식 근거; 현재 V657 합산 29, 추가 20곳 필요 |
| 카드번호·HIT·프로모·희귀도 정확성 | 20 | 30게임 중 20게임 이상 제조사 ID 기반 교차 확인, 불명확한 판본 격리 |
| 국가별 매입/판매/체결 시세 | 15 | 자료 링크, 수집시각, 통화, 타입을 반드시 분리; 가격 오표기 0 |
| 행사·프로모 중복 정합성 | 10 | 같은 분류 내부에서만 중복 통합, 모든 독립 출처 추적 |
| 보안·성능·Python/Node·CodeQL CI | 20 | 최신 HEAD 전체 검증 및 관련 결함 0 |
| Lenovo Termux·오프라인·재부팅·렉 | 10 | 실기기에서 완주 증거 |
| **총점** | **120** | **100점 이상은 위 실측과 차단 게이트 통과 후에만 인증** |

무료 REST API 사용권≠재배포 권한. 403/429 차단 우회 금지, 업그레이드·결제 차단, API 키 필수화 금지. 모방 앱 소스는 합법적 구조와 원칙만 참고.

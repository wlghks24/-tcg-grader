# V662 무료 TCG 수집 범위·공식 BOX 공백 보완 검증 보고

기준 2026-10-12(KST). 저장소 `wlghks24/-tcg-grader`, PR #651 Draft/HOLD. 본 파일과 신규 근거가 들어간 것은 main 배포·태블릿 실기기 인증이 아님.

## 검증된 제조사 일본 BOX 3종

1. **MTG Japan market – Lorwyn Eclipsed Play Booster Display:** https://magic.wizards.com/ja/news/feature/collecting-lorwyn-eclipsed (30팩/BOX, 실제 게임 카드 14장/팩). 출시 2026-01-23 확인 https://magic.wizards.com/ja/news/announcements/everything-announced-for-magic-the-gathering-in-2026. 일본 공식 사이트 제품 안내 근거로 일본 시장 범위에 등록; *제품 자체의 일본어판/영어판 SKU·바코드는 미확인*이므로 `LOCAL-` 임시코드이며 일본어판 특정 SKU로 단정하지 않음.
2. **Weiß Schwarz JP – アサルトリリィ Last Bullet:** https://ws-tcg.com/products/all_bplb/ (12팩/BOX×8장, 발매 2026-02-27, 제조사 BOX 정가 JPY 5,280 세금 포함). 신품정가를 실거래가로 승격 금지; BOX 특전 PR은 HIT 랜덤봉입 확률이 아님.
3. **Dragon Ball Super Fusion World JP – CROSS FORCE FB10:** https://www.dbs-cardgame.com/fw/jp/events/01_446.html (24팩/BOX). 반다이 제품 https://www.dbs-cardgame.com/fw/jp/products/01_400.html (6장/팩, 별도 디지털 코드 1장 제외, 2026-06-13). 행사 수량/낱팩 정가를 BOX 정가나 실제 체결가로 추정하지 않음.

## 기존 표본 보존과 데이터 합산

| 지표 | V661 | V662 보강포함 |
|---|---:|---:|
| 제조사 제품 예시 | 96 | **99** |
| 일반 부스터 BOX 예시 | 59 | **62** |
| 등록 게임×국가 범위 | 55 | 55 |
| 최소 한 개 공식 BOX가 있는 범위 | 31 | **34** |
| 공식 일반 BOX 예시 공백 | 24 | **21** |
| 30게임×3국가×6부문 조사 | 540 | 540 |
| 원본 게임·미검증 후보 | 30게임·338후보 | 변경 없이 보존 |

자료 99개는 시장 전체 상품 개수가 아니며 '어떤 한 게임×국가에 표본 한 BOX'라는 제한이 있다. 55개 지역 중 34개에 최소 한 개 표본이 있다는 의미일 뿐 전체 발매 세트 커버율 61.8%가 아니다.

## 기술 변경

- `tcg_official_product_supplement_v662.json`: 3개 공식 제조사 원문, 수량, 출시일, 국가와 통화 단위.
- `tcg_official_overlay_v662.py`: 하드코딩한 게임·국가·세트·상품명·팩수·팩당 카드수·원문 URL·출시일·제조사 정가를 **정확히** 대조하고 다른 임의 MSRP, 가짜 실거래가, 중복 ID, SKU 과장 거부. V659 보강의 자식.
- `tcg_multi_source_queue_v639.py`, `tcg_source_audit_v633.py`: 30게임 오프라인 수집/자료부족 우선순위에만 순차 추가. V662 누락 시 기존 V661/96건 정상 유지.
- `official_box_catalog_v626.js`, `tcg_source_research_v634.js`, `tcg_coverage_radar_v652.js`, `tcg_30_game_catalog_v629.js`: 태블릿 UI에도 V662 부모체인 검증/보강 연결, 실패 시 이전 정상데이터만 표시.
- `test_tcg_v662_official_box.py`: 99/62/21/34/55 통계, 제품 구성, 모조 도메인, 잘못된 가격·제품명, 기존 96건 fallback, JS 간 통계 일치 검사를 작성.
- `.github/workflows/tcg-free-collector-qa.yml`에서 새 Python 컴파일/회귀검사 등록, 변경 파일 SHA256은 `integrity_manifest.json`에 기록.

## 직접 재실행 증거 범위

브라우저 없는 V8 환경에서 **실제 저장소 JS 소스 함수**를 실행해 99/62/21 / 540개 조사작업 / 30게임 카드 목록 건수 99 / 96 정상 fallback / 허위 `ws-tcg.com.attacker.example` 기각을 확인했다.

**이 턴에서 Python 전체 unittest/Node.js 테스트 커맨드를 실제 실행한 결과, 최신 HEAD GitHub Actions/CodeQL 성공 로그, Lenovo Android/Termux 설치·장시간 성능 수치는 확보하지 못했다.** CI에 테스트 코드 추가는 CI PASS가 아님. 확인 전 PR #651은 Draft/HOLD, main 병합 금지.

## 다음 인증 차단요소

- 기존 운영의 100+/120 목표에 따라 활동 지역 54개 중 최소 49개 BOX 표본 기준이라면 신규 표본 34/55에서 *현재 운영중인 54지역 중 49곳*을 보장하려면 적어도 **15개 추가 지역**의 제조사 증거 확보. WIXOSS US 중단/역사판은 집계에서 별도 제외.
- 공식 카드번호·수록 희귀도는 2게임 3건 초기 자료에 그쳐 최소 20게임 제조사 카드DB 교차확인이 필요. 공개 TCGdex/V661 카드번호와 제조사 확인은 별도.
- 매입/판매등록/실제 완료거래 증거 구분 유지; 완료거래 주장만으로 실제 체결가격 인덱스 입력 금지.
- 무료 제공 여부 및 상업적 이용권 별도. 차단된 API 403·429 무단 우회 금지, 자동 과금·유료 의존 추가 금지.

### 참고 명령
```sh
python tcg_official_overlay_v662.py
python -m unittest -v test_tcg_v662_official_box test_tcg_v659_v660 test_tcg_v658_alignment
python tcg_multi_source_queue_v639.py --format summary
python tcg_source_audit_v633.py --summary-only
```

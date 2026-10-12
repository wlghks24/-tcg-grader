# V675 — 무료 경쟁 앱 근거와 시세 증거·한국시간 CSV 교차검증

검토 기준: 2026-10-13 KST. 상태: **DRAFT / HEAD CI·Lenovo 실기기 미확인.** 이 문서는 실제 매매·결제·등급 정확도 인증이 아닙니다.

## 관찰한 외부 사례(공식 출처 우선)
- TCGplayer는 **Market Price(완료 거래 기반)**, **Most Recent Sale**, **Listed Median(현재 호가)**를 분리한다: https://help.tcgplayer.com/hc/en-us/articles/222376867-What-do-the-different-price-points-on-TCGplayer-com-mean
- PriceCharting은 완료 판매 목록, 최근성, 이상치, 오분류 수동 신고를 가격 계산에 고려한다: https://www.pricecharting.com/page/methodology
- CollX는 스캔에서 재발행·패러렐을 구분해 사용자가 확정하도록 한다. 최근 판매 10건·6개월 중앙값 정책을 설명한다: https://collx.app/faq
- TCGdex는 무료 다국어 카드/세트 검색 경로지만 현재 한국어 지원은 *coming soon*으로 표기한다. API로 한국 정식 BOX 사양이나 확정 실거래를 가정하지 않는다: https://tcgdex.dev/
- JustTCG 무료 API는 1,000회/월, 100회/일, 10회/분이며 **비상업 개인 용도**에 국한된다. 판매/상업 서비스에 무료 플랜을 상업 라이선스로 가장해 연결하지 않는다: https://justtcg.com/ 와 https://justtcg.com/docs/rate-limits
- PSA 공식 등급 기준은 표면·코너·센터링 등을 명시한다. 이미지 AI 점수=PSA 발급 등급이 아니다: https://www.psacard.com/gradingstandards

## 이번 보완
1. `tcg_market_evidence_audit_v674.py`: 출처 URL 없는 서로 다른 주장 금액을 서로 다른 시장 출처로 세지 않고 **동일 익명 출처의 가격 충돌**로 격리한다. 참조 링크가 있는 독립 자료만 각기 별도 표본으로 계산한다. 시장 가격표 공개 자격은 계속 false.
2. `tcg_source_staging_v642.py`: GitHub UTC runner와 Android/Termux 한국시간 차이로 00:00~08:59 KST 같은 날짜 증거가 미래로 기각되는 문제를 막기 위해 기본 기준일을 KST로 통일한다.
3. V674·V642 반례 단위 테스트 및 V664 오프라인 preflight에 회귀검사 대상 추가. 수집기 무료 Python 표준 라이브러리만 사용.

## 검증 상태 / 품질 문턱
- 코드는 PR 브랜치용 변경, `main` 병합 없음. HTTP 우회·유료 API·정산 증명 자동 판정 없음.
- 목표: Python 전체 테스트 + 동일 HEAD Actions + CodeQL 성공 로그 확인. 미확인 상태는 PASS로 기록하지 않는다.
- 실거래 플랫폼 SOLD 표시는 결제 정산과 구별하며, 출처 없는 사용자 가격 제보는 검증 시세가 아니다.
- 기존 제조사 공식 BOX 105제품/68 BOX/39/55 지역/16공백은 V671 증거 스냅샷; 이번 수정은 수치를 늘리는 작업이 아니다.
- 남은 P0: 공식 BOX 공백, 정산까지 확인된 독립 체결가격, Lenovo 실기기 장시간 시험, 라이선스/출처 지속 점검.

# V627 · 무료 공식 BOX 자료 확장 및 부족한 증거의 품질 평가

기준일 2026-10-12 · 대상 `wlghks24/-tcg-grader` · **제조사 제품 사양·카드별 HIT·시장 거래 증거는 서로 독립**

## 실제 변경

기존 `main`에서 공식 제품 표본 **47건, 10개 TCG, 등록된 게임·국가 55조합 중 표본 11조합, 빈 지역 44조합**. V627의 새 MTG 미국 자료 검증 후 예상 값은 **53건, 11개 TCG, 12/55조합, 빈 지역 43조합**이다. 저장된 상품 한 건으로 그 나라 전체 BOX를 수집했다고 해석해서는 안 됨.

MTG 공식 상세페이지를 통해 2026년 세트의 **BOX 자체의 팩 수**를 검증했다.

| MTG 미국 공식 세트 | 발매일 | Play Booster BOX | Collector Booster BOX | 제조사 직접 원문 |
|---|---|---|---|---|
| Lorwyn Eclipsed | 2026-01-23 | 30팩 × 14장 | 12팩 × 15장 | https://magic.wizards.com/en/news/feature/collecting-lorwyn-eclipsed |
| Secrets of Strixhaven | 2026-04-24 | 30팩 × 14장 | 12팩 × 15장 | https://magic.wizards.com/en/news/feature/collecting-secrets-of-strixhaven |
| Reality Fracture | 2026-10-02 | 30팩 × 14장 | 12팩 × 15장 | https://magic.wizards.com/en/news/feature/collecting-reality-fracture |

MTG 추가 6개 항목은 실제 원문을 확인한 날짜 `source_checked_at: 2026-10-12`를 기록했으며, 기존 47개 항목은 검토일을 소급해서 만들어 넣지 않았다. 상품 원문을 웹에서 확인했다는 기록은 카드별 재고·실거래 인증을 의미하지 않는다.

상품별 **BOX MSRP(희망판매가격)**가 입증되지 않아 BOX 가격 필드는 공란. 낱팩 MSRP를 BOX 가격으로 임의 환산·입력하지 않는다. `LOCAL-FRA-PLAY-BOX` 등의 세트식별자는 **앱 내부 식별자**이며 공식 카드 수록 세트 코드(FRA/ECL/SOS)를 대체한다고 주장하지 않는다. 시리얼 넘버 카드 존재(공식 출처 확인)는 무작위 1BOX에서 해당 카드가 보장된다는 의미가 아님.

## 시중 앱 비교: 취사선택

- **TCGplayer Scanner:** 같은 그림의 다른 세트·판본을 잘못 구분할 수 있음을 FAQ에 고지하고 인쇄판/언어/상태를 사람이 재확인하도록 함. https://help.tcgplayer.com/hc/en-us/articles/115009506407-TCGplayer-App-FAQ . V618 후보 판본 차단과 V620 보류 중인 진짜 OCR 판본 충돌 검사 유지. 확인되지 않은 판본은 시세 자동 연결하지 않음.
- **Collectr:** 개인 포트폴리오에 sealed BOX와 단일 카드를 별도 저장하고 통화·게임·수량 필터 제공. 일부 고급 기능은 무료가 아니므로 유료 기능 의존 불허. https://www.getcollectr.com/track.html . 공식 BOX 정보 목록 ≠ 현재 보유 재고 목록, 시장가격 ≠ 제조사 정가.
- **Scryfall:** MTG 무료 API는 429 및 10req/s 미만 제한을 공식 안내. 대량 조회는 bulk 데이터 권장. https://scryfall.com/docs/faqs/i-m-having-trouble-accessing-the-scryfall-api-or-i-m-blocked-17 . 무제한 무료 자동수집을 가정하거나 429 우회 VPN 재시도를 구현하지 않음. 별도 약관 검토 후 캐시와 요청 빈도 제한을 조건으로 후보 검토.

## 새 자료 품질 점검: `official_product_evidence_audit_v627.py`

표본이 늘어날수록 출처/세부 정보 결측을 숨기는 대신 **모든 상품마다** 다음을 평가:
- 제품 상세 또는 제조사 기사 URL과 제조사 **제품 카테고리 목록만 연결된 URL** 구별. 이는 URL 구조를 이용한 **검토 우선순위 힌트**이지 출처 원문 내용을 독립 재검증했다는 뜻이 아님.
- BOX 또는 PACK 실제 출시일, 팩 수, 팩당 카드 수, BOX/PACK 각각 정가, 임시 세트코드 여부, 마지막 원문 재확인 시각.
- 실제 완료 거래·HIT 확률·실시간 매장 재고·전체 수록 카드 리스트는 **기본 미인증**. 잘못된 제품 출처나 중복 ID는 기존 V623 검증기로 보류.
- 빈 게임·지역 조합, 1개만 확보된 지역과 진정한 전종 수집 완료를 구분.

로컬에서:
```bash
python -m unittest -v test_official_mtg_evidence_v627.py test_official_product_catalog_v599.py test_official_box_coverage_v623.py test_official_box_catalog_v626.py test_tcg_user_research_intake_v625.py
python official_product_evidence_audit_v627.py --output local_official_product_review_queue.json
```
기존 정적 HTML 공식상품 뷰어 `official_box_catalog_v626.html`은 게임 "Magic: The Gathering"을 목록에 포함하고 BOX만 필터 가능. **실제 Lenovo 태블릿 브라우저 실행 여부는 미검증**.

## 다음 개선 우선순위 (무료만)

1. 이 레포지토리 게임·국가별 **빈 43조합** 중 실제 제조사 공식 상품 존재 여부 검증, 문서 링크/최종 확인일/원문 상세페이지 확보.
2. BOX별 전체 카드리스트, 카드번호·레어도·일반/패러렐·인쇄판·언어 차이 정확히 연결. TCGplayer의 판본/상태 수동 확인 UX 수준까지 정량 테스트.
3. HIT는 제조사 공개 개봉 슬롯 확률과 일반적인 임의 추측 분리. MTG의 시리얼 카드 500장 존재는 BOX당 당첨 확률이 아님.
4. 체결 완료 거래 ID·통화·발생 시각·판매처·개봉/재포장 상태가 있는 경우만 BOX 실거래 가격으로 승인. 단순 호가와 제조사 정가는 분리.
5. 유저에게 100점 넘는 품질 점수를 보여주려면 실기기 터치·오프라인·최악 게임별 인식·RAW 실감정 보정쌍·유료요금 0원 등을 **각각 실측 증명**. 데이터 건수 증가만으로 점수 인증 금지.

모든 신규 기능은 **별도 과금/유료 API/클라우드/인앱 결제 없이 로컬 Python/JavaScript**로 동작. 출처 원문에 있는 이미지의 재사용 허가는 이번 작업 범위에 포함되지 않음.

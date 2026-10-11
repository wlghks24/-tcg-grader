# V625 사용자 제공 30종 카드게임 자료 대조 및 수집 우선순위

검토일: 2026-10-12 KST. **주신 30개 게임의 상품명·HIT·프로모를 검증된 판매상품/거래증빙으로 오인하지 않는 것이 우선**입니다.

## 보관 방식
- `tcg_user_research_intake_v625.json`: 사용자 제공 30개 게임, 상품/세트 후보 198개, 출시예정 후보 42개, HIT 이름 60개, 프로모 38개를 **USER_SUBMITTED_UNVERIFIED**로 등록.
- 이 후보는 자동으로 `market_prices.json` 또는 `tcg_official_product_catalog_v599.json`에 복사하지 않습니다. 정가·HIT 확률·실거래·재고·PSA 등급은 근거가 없으면 공란.
- `tcg_official_product_catalog_v599.json`: 공식 원문 확인을 거친 항목만 등록. V624+V625 후보 브랜치 기준 **47개 제품, 10개 카드게임, 지역 표본 11/55**. **44개 지역 공백**.
- `test_tcg_user_research_intake_v625.py`: 30개 게임 레지스트리 대조, 후보→공식 상품/가격 자동 승격 금지 확인.

## 즉시 바로잡아야 하는 8가지
| 사용자가 제공한 요약 | 실제 확인된 내용 / 앱 반영 규칙 | 제조사·공식 출처 |
|---|---|---|
| 건담은 독자 TCG 단종, Union Arena 중심 | **GUNDAM CARD GAME 독립 제품 출시 중**. Union Arena의 건담 IP 참전과 별도 제품·상품종류로 분리 | https://www.gundam-gcg.com/en/products/list.php?page=1 |
| 고질라 독자게임 없음 | 2025년 출시 독립 **Godzilla Card Game** 운영 중. EBP01(2025-07-05), EBP03(2026-01-31), EBP04(2026-05-23) 제조사 공식 상품 등록 | https://en.godzilla-cardgame.com/products/ |
| 팰월드 1탄만 판매, 2탄 이름 Night of the Syndicate | **Dawn of Palpagos**(2026-07-30), **Legends Awaken**(2026-10-30 예정) 공식 확인. Night of the Syndicate는 사용자 조사 후보로만 보관 | https://en.palworld-official-cardgame.com/products |
| MetaZoo 2024 단종, 앞으로 발매 없음 | 2025년 재출범, **2026-06-26 MetaZoo 공식 신규 홈페이지·카드 DB 발표**. 예전 단종 판정 유지 금지. 현재 판매·BOX 구성은 별도 확인 | https://www.metazootcg.com/news/metazoo-launches-new-website |
| Bandai NARUTO, Union Arena Naruto, 중국 Kayou 동일 게임 | **별개의 게임·상품 플랫폼**. Bandai 신규 NARUTO CARD GAME은 **2027년 여름** 전세계 출시 예정 | https://www.naruto-cardgame.com/en/ |
| MTG 스파이더맨 2026 출시 예정, 스타트렉 전부 미정 | Spider-Man은 **2025-09-26 출시**. Star Trek **Beginner Box만** 2026-09-21 취소 공지. 기타 Star Trek 상품 전체 취소 아님 | https://magic.wizards.com/en/news/feature/spider-man-prerelease-guide , https://magic.wizards.com/en/news/announcements/statement-on-the-cancellation-of-the-star-trek-beginner-box |
| Lorcana Hyperia City 시기 모호 | 프리릴리즈 **2026-10-16**, 일반 세트 출시 **2026-10-23**, 프리릴리즈 BOX에 **6팩**. 행사일과 일반 매장 출시일 별도 저장 | https://www.disneylorcana.com/en-US/product/hyperia-city , https://www.disneylorcana.com/en-US/news/2026/10/hyperia-city-prerelease-guide |
| Riftbound Vendetta, Spiritforged 신규 출시 예정 | 제조사 2026 로드맵에서 **Vendetta 2026-07-31 출시**. Spiritforged도 일부 지역 발매 진행. 이후 로드맵 별도 확인 | https://riftbound.leagueoflegends.com/en-us/news/announcements/riftbounds-latest-2026-roadmap/ |

## 실제로 추가 확인한 V625 제품 6개

| 게임 | 공식 상품/종류 | 미국 발매/예정 | 확인되지 않은 것 |
|---|---|---|---|
| Godzilla Card Game | EBP01 Godzilla vs. Godzilla / booster | 2025-07-05 | BOX 팩수, 개별 HIT 확률 |
| Godzilla Card Game | EBP03 Resonance of Rivals / booster | 2026-01-31 | BOX 팩수, 거래가 |
| Godzilla Card Game | EBP04 Endless Wars / booster | 2026-05-23 | BOX 팩수, 거래가 |
| Palworld OCG | BP01 Dawn of Palpagos / booster display | 2026-07-30 | 실거래·매장별 재고, 구매 캠페인 확률 |
| Palworld OCG | BP02 Legends Awaken / booster | 2026-10-30 예정 | BOX 구성, 카드 세부 레어리티별 확률 |
| Disney Lorcana | Hyperia City Prerelease Box (6팩) | 2026-10-16 행사 예정 | BOX 권장가와 개별 시판 시작일 |

**주의:** Godzilla 게임 제품은 MTG Ikoria 고질라 일러스트 카드와 섞지 않습니다. Palworld 제품도 Union Arena 콜라보나 PalVerse 굿즈와 섞지 않습니다. 스탬프 사인은 인쇄·복제 사인일 수 있으므로 실물 친필 서명이라는 표현을 공식 증빙 없이 붙이지 않습니다. 이벤트 프로모는 구매조건 증거 없이 BOX 랜덤 HIT로 취급하지 않습니다.

## 다음 검증 우선순위
1. 공식 카드리스트의 세트별 카드 번호/언어/일반·패러렐·레어리티가 정확하게 일치하는 후보부터 확인 (Godzilla EBP, Palworld BP01, Pokémon 세트별).
2. 나머지 WATCH 게임의 제조사 공식 세트/프로모 URL 수집. 해당 게임이 독립 TCG인지 IP 콜라보인지 반드시 구분.
3. 국가별 팩/BOX·출시·가격이 달라지므로 KR/JP/US 정가, 호가, **완료거래**를 별도로 기록.
4. UI의 공식상품 허용 호스트와 JPY 통화 표시, 100건 잘라내기 문제는 기존 감시 대상 JS 변경이므로 별도 후속 검증이 필요. 저장소 CI와 실제 태블릿 UI 테스트를 모두 통과하기 전에는 UI 해결 완료라고 표시하지 않음.

전체 조건은 **추가 유료 API·서버·클라우드 없음**. 단, 공식 원문·API 호출과 카드 이미지의 이용약관·라이선스는 공급자별로 따로 준수합니다. 완성도 100+20점은 내부 목표이고 **실제 점수 미채점** 유지.

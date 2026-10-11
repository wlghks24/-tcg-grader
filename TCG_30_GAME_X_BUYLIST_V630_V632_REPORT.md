# V630–V632 · TCG Grader 무료 30게임 × 3국가 BOX·매입 제시가 검색 정밀 검토

검토일: 2026-10-12 KST · 대상 PR #651 (draft, main 미반영)

## 기존 자료 전수 보존 / 범위 정정

- `tcg_game_registry.json`: 30종 / 30종.
- `tcg_user_research_intake_v625.json`: 30종의 198개 BOX·상품·세트 후보, 42개 출시예정, 60개 HIT 이름, 38개 프로모 이름 보존. **사용자 입력 후보는 공식 확정 자료가 아님**.
- 제조사 샘플 원본 `tcg_official_product_catalog_v599.json` 58건은 기존 핀 고정 상태. V630 공식 보강 5건을 **별도 파일** `tcg_official_product_supplement_v630.json`에 추가. 합산 63건, 17게임, 공식 지역별 제품 샘플 19/55, 미수록 조합 36. 샘플이 있다고 완전한 세트 수록 카드가 확보되었다는 뜻은 아님.
- `official_box_catalog_v626.js`는 58 + 5건을 조건부 로드하고, 보강 파일 실패 시 기본 목록을 유지하면서 로드 실패를 표시함. `tcg_30_game_catalog_v629.js`의 게임별 제조사 기록 수에도 보강 샘플 반영.
- 추가: Flesh and Blood Super Slam US 영문판 24×15 $119.90, JP 일본어판 24×9 ¥5,760(인쇄판별 구분), FFTCG Blissful Eternity US 18×12, Vanguard Envoys of the Crimson Moon / Parallactic Dawn 미국판 각 16×7. **정가와 매입 제시가/중고 거래시세는 별개**.

## 6게임 제한 해제 → 30게임 × 3국가 검색

- `tcg_x_buylist_search_v631.py`: 30개 게임 ID를 **저장된 레지스트리에서 동적 로딩**, 지역 JP/KR/US별 쿼리 90개, BOX 검색도 90개. 사용자 요청 6종뿐 아니라 유희왕, 유니온, 디지몬, 바이스, 포켓몬, 원피스 외 나루토·건담·MTG·로카나·팔월드·고질라·리프트바운드 등 등록된 **모든 30종** 처리.
- 일본어 단축 검색어 6종: ポケカ / ワンピカード / 遊戯王 / ヴァイス / ユニアリ / デジカ. 나머지 24종은 검증 전까지 지정 검색 별칭/공식 등록명으로 광범위 검색. **공식 약칭이나 최고가 레어도를 임의로 인증하지 않음**.
- JP: 買取, 買取表 / -販売 -オリパ -トレード -プレゼント -交換希望
- KR: 매입, 매입가, 삽니다 / -판매 -오리파 -교환 -나눔 -이벤트
- US: buylist, "we buy", "buying cards" / -giveaway -raffle -"trade only" -"for sale" -"mystery box"
- 카드: 전체 검색을 기본값으로 하며, 검증되지 않은 레어도는 필터 강제 금지. 포켓몬 SAR/UR(미국판 SIR), 원피스 コミパラ/Manga Rare, 일본 유희왕 クオシク 등 **검색 힌트**만 선택 가능. 카드의 실제 최고가 순위 의미 아님.
- BOX: 로컬 별칭 (일본 BOX/ボックス/未開封, 한국 BOX/박스/미개봉, 미국 "booster box"/"sealed box"/sealed). BOX 매입 공고 검색은 BOX 정가/실거래가 판단이 아님.
- 전체 90개국가-게임 검색 가능. 기존 레지스트리에 정식 범위로 선언된 55쌍과 **미선언 35쌍**을 `declared_region`으로 구분. 35쌍은 존재를 주장하는 것이 아니라 탐색 목적. `--declared-only`로 55쌍만 생성할 수도 있음.
- X 검색 연산자는 공식 X 고급 검색 안내에서 지원하는 검색 제외어, OR, `filter:images` 등을 이용. `lang:ja/ko/en`은 혼합언어 결과 누락 방지를 위해 기본 비활성; 필요한 경우 Python `--language-filter`.
- `tcg_x_buylist_v632.html` + `.js`: 태블릿 무료 브라우저 화면, 30종 게임 선택, 3국가, 카드/BOX, 6종 레어도 힌트, X 검색 링크. 공식 BOX/30종 입력뷰에서 이동 가능. 외부 JS 라이브러리, 유료 클라우드, X API, 자동 스크래핑 사용 없음.

## 복사용 Python 실행 예

```sh
python tcg_x_buylist_search_v631.py --game all --region ALL --kind card
python tcg_x_buylist_search_v631.py --game all --region ALL --kind box
python tcg_x_buylist_search_v631.py --game onepiece --region JP --rarity コミパラ
python tcg_x_buylist_search_v631.py --game pokemon --region KR --kind box
python tcg_x_buylist_search_v631.py --declared-only
```

```python
from tcg_x_buylist_search_v631 import tcg_search_config, generate_twitter_query, generate_twitter_url
print(len(tcg_search_config))             # 30
print(generate_twitter_query("onepiece", "コミパラ", region="JP"))
print(generate_twitter_url("pokemon", region="US", kind="box"))
```

## 120점 목표: 점수는 실측할 때만 부여

| 배점 | 승인 기준 | V632 작업 상태 |
|---:|---|---|
| 20 | 사용자 30게임 × BOX/HIT/프로모 자료 보존·조회 | 소스·UI 점검, 신설 테스트 |
| 20 | 3국가 90범위 카드/BOX 검색과 국가 범위 구분 | Python·태블릿 UI 및 parity 테스트 **작성** |
| 20 | 제조사 공식 BOX 국가/구성/날짜/정가 전수 검증 | 63개 **샘플**, 17/30 게임에만 존재, 미완료 |
| 15 | 매장 매입 제시가/실거래/호가/정가 출처·날짜·상태 구분 | 조회 설계만, 실제 가격 수집·검증 미구현 |
| 15 | 보안·검색어 인젝션 방지·외부 유료 서비스 0건 | 정적 코드 제어 작성, CI 미확인 |
| 15 | 통합 및 회귀 검사 실제 통과 | 최신 HEAD CI 결과 아직 없음 → 미채점 |
| 10 | Lenovo 실기기 화면·성능·접근성 검증 | 미실행 → 미채점 |
| 5 | 설치/운영 시 강제 결제 없는 핵심 경로 | Python 표준 라이브러리 / 정적 JS 기반 (X 사이트 자체 정책 변화는 별개) |
| **120** | **100점 이상은 실제 검증 후** | 현재 **인증 점수 부여 불가**, main 병합 HOLD |

## 남은 리스크 / 정확성 기준

1. `買取` 가격은 점포가 제시한 **매입 희망가**로, 판매 희망가·체결가·낙찰가·실재고·PSA 확정가와 구분. 통화 JPY/KRW/USD, 카드 판본·상태·매장·작성시각·정확한 상품 ID 확인 필요.
2. 일본·한국·미국 검색 시장은 지역 언어의 키워드이며 **해당 게임이 3개국에서 정식 출시**되었다는 증거가 아님.
3. -販売 / -판매 / -"for sale" 필터는 정확도는 올릴 수 있지만 매입·판매 병기 매장 공고를 놓칠 수 있음. 광범위 스캔 시 제외 키워드 조정 별도 평가 필요.
4. 이용자가 X 검색 링크를 열어 직접 조사하는 기능이며, 자동 실시간 가격 갱신·X 자동 크롤러 기능이 아님. 사이트 이용약관·API/로그인 조건 준수.
5. 정식 배포에는 PR HEAD 기준 10개 계열 체크·코드 정적분석·전체 회귀·무결성·Tablet Alignment·실기기 검사 필요. 미확인 사항은 자동승인 금지.

참고 출처:
- https://help.x.com/en/using-x/x-advanced-search
- https://help.x.com/ko/using-x/advanced-xpro-features
- https://help.tcgplayer.com/hc/en-us/articles/16007140992791-Price-Settings-and-Updates
- https://legacy.fabtcg.com/en/products/booster-set/super-slam/
- https://fftcg.square-enix-games.com/na/release/blissful-eternity
- https://en.cf-vanguard.com/products/dz-bt14/
- https://en.cf-vanguard.com/products/dzbt16/

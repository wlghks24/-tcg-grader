# V644–V647: 카드 30종 이벤트·프로모·경품·콜라보·영화 통합 조사 및 다중 출처 병합

작성일: 2026-10-12 KST · GitHub PR #651 **draft** · main 미배포

## 작업 목적 및 무료 제약

- 카드 30게임 × 한국/일본/미국 90개 조사 범위 × 행사 11분류 = **990개 카테고리 조사 경로** (등록 지역 55×11=605, 미선언 판본은 검색용만). 각 범위에 제조사 Google/Bing, 웹 전체 Google, Instagram 색인, YouTube 색인, X 최신 **6종 검색 경로**.
- 행사 종류: `PROMO` 카드, `EVENT` 행사, `TOURNAMENT` 대회·참가상, `COLLAB` 협업, `MOVIE` 영화/극장판, `GIVEAWAY` 경품/무료 증정, `GIFT` 사은품/구매 특전, `LOTTERY` 추첨, `POPUP` 팝업, `FESTIVAL` 축제/박람회, `PRERELEASE` 프리릴리즈.
- 전부 Python 표준 라이브러리 및 기본 브라우저 기능. **기본 외부 API/네트워크 요청은 0건**. YouTube·Instagram·X 자동 로그인/스크랩·403/429 우회·경품 자동 응모·유료전환 없음.
- 검색 작업 수 990건을 **실제 수집 완료한 이벤트 990건으로 오인해서는 안 됨**. 공식 홈페이지가 이벤트 공지를 게시할 때만 원문에서 행사 장소·일자·경품/참가조건을 확인.

## 실제 사례 검토: 포켓몬 30주년 공식 이벤트

공식 출처:
- 포켓몬 30주년 행사 목록: https://www.30th.pokemon-card.com/event
- 30th 프로모 카드팩 짐배틀 지급 상세: https://www.30th.pokemon-card.com/event/30thgym
- 30th 메달 그랑프리 공식 상세: https://www.30th.pokemon-card.com/event/30thgym-02

`tcg_event_source_sightings_v645.csv`/`.json`에 **실제 공식 게시물 기반 5개 발견 기록**:
1. 일본 30th 프로모팩 짐배틀 참가 지급, 2026-09-16~2027-01-31, 상세 페이지 · 공식 발견
2. **동일 행사**를 공식 행사 색인 페이지에서 발견, 다른 검색 키워드/Google 발견
3. **동일 상세 URL**을 Bing에서 재발견했지만 `utm_source` 파라미터만 다름
4. 일본 30th CELEBRATION 메달 그랑프리, 2026-10-20~2027-01-31 예정, 30th 메달 등
5. 일본 30th CELEBRATION EVENT 지바 개최 2026-10-25 (마쿠하리 메세)

중복 통합 결과: **5개 발견 기록 → 3개 개별 이벤트, 해당 이벤트별 고유 출처 URL 연결 4개**.
첫 행사에는 **상세 URL과 행사 목록 URL 2개를 모두 표시**하며, 상세 URL에서 찾은 경로 `official, bing` 2개 및 출처별 검색 키워드, 원본 입력 파일과 행번호, 확인일을 보존. 실제 출처 URL 자체는 모두 클릭해 직접 확인할 수 있음.

## 중복 제거/근거 검증 규칙

- Unicode NFKC 정규화로 띄어쓰기/구두점·일부 표기 차이를 통일. 통합 키는 **게임ID + 국가 + 행사유형 + 정규화한 제목 + 시작일 + 장소**.
- **시작일이 미확인인 글은 제목이 같더라도 서로 다른 URL이면 자동으로 합치지 않음**. 임의 행사일/시작시각을 추정하지 않는다.
- 같은 URL은 `utm_*`, `fbclid`, `gclid`, `igshid` 등 추적 파라미터를 버린 주소로 묶되, `id`, `page`, `lang` 등 본문 구분 쿼리는 유지.
- 같은 상세 URL에서 찾은 **Google/Bing/공식/Instagram/YouTube/X 발견 경로와 키워드**, 파일/행 출처는 모두 남긴다. 출처 페이지가 중복되지 않으면서 행사 레코드에도 목록 URL이 누락되지 않는다.
- 다른 국가, 행사 날짜, 오프라인 지점, 유형은 자동 병합하지 않고 `possible_duplicate_review` 대기. 키워드만 동일한 unrelated 영화·콜라보·경품을 허위로 합치지 않는다.
- 제조사 도메인 허용 목록 통과는 **사이트 소유 계열의 근거**일 뿐 게시 내용 또는 지급 이벤트 검증 완료가 아님. `confirmed:false` 고정, 차단/사칭 URL 등은 수동 검증 대상으로만 노출.
- 대량 후보 간 전수 제곱 비교 대신 **제목/키워드 역색인** 사용하고 유사 후보 결과 1,000개 한도로 제한해 Termux 메모리/렉 보호.

## 실제 반영 파일

| 파일 | 새 기능 |
|---|---|
| `tcg_event_intelligence_v644.py` | 30×3×11 키워드 조사 링크와 CSV 중복 병합, 출처별 증거 보존, 수동 검증 리포트 |
| `tcg_event_source_sightings_v645.csv`/`.json` | 5개 실 출처 발견 기록, 3개 공식 행사 시나리오, 동일 URL Bing/공식 재발견 |
| `tcg_event_intelligence_v646.js`/`.html` | 태블릿 30종 행사·영화·경품 필터, 단일 이벤트 아래 출처 전체/발견채널/키워드 표기, 로컬 JSON 가져오기·저장 |
| `test_tcg_event_intelligence_v646.py` | 990/605 검색범위, 오탐 병합 금지, 공식 출처·HTTP URL 검증, JS/Python 실 데이터 병합 회귀 |
| `tcg_event_rss_v647.py` | 사용자가 확보한 RSS/Atom XML 파일 최대 12개를 오프라인으로 읽어 11개 행사 카테고리에 자동 분류. 본문 미수집·DTD 금지·출처 HTTPS 확인 |
| `test_tcg_event_rss_v647.py` | RSS/Atom XML 검증, 중복 URL, 영화·콜라보·경품 자동 분류, 악성 XML 차단 및 행사 날짜 추정 금지 |

**RSS 발표 날짜는 행사 시작일이 아니므로** RSS 단계의 `start_date`는 비워둔다. 행사 기간이 공식 상세에 확인되면 그 정보를 CSV에 입력한 후에야 여러 출처의 같은 행사를 묶을 수 있다. 부정확한 자동 완결보다 누락 경고와 원문 출처 보존을 우선한다.

## 태블릿/Termux 무료 사용

```sh
# 설치된 기존 저장소 폴더에서
python tcg_event_intelligence_v644.py --plan --summary-only
python tcg_event_intelligence_v644.py --plan --game pokemon --region JP --category PROMO
python tcg_event_intelligence_v644.py --input tcg_event_source_sightings_v645.csv --output ./export/event_merged.json
python tcg_event_intelligence_v644.py --input ./export/other_news.csv --input tcg_event_source_sightings_v645.csv --output ./export/event_merged_all.json

# 이미 다운로드한 RSS/Atom XML 파일을 표준 라이브러리로 분류
python tcg_event_rss_v647.py --feed ./downloads/events.xml --game pokemon --region JP --format csv --output ./export/rss_event_leads.csv
python tcg_event_intelligence_v644.py --input ./export/rss_event_leads.csv --input tcg_event_source_sightings_v645.csv --output ./export/combined.json

# 검증
python -m unittest -v test_tcg_event_intelligence_v646.py test_tcg_event_rss_v647.py
node --check tcg_event_intelligence_v646.js
```

웹 `tcg_event_intelligence_v646.html`에서 기존 예시 3건을 통합 표시하고, 추가로 처리한 `event_merged.json`은 브라우저 기기 내부 파일 가져오기로 표시. 채팅이나 서버에 자동 업로드하지 않는다.

## 100+/120 목표의 추가 품질 평가

| 영역 | 배점 | 통과 증거 |
|---|---:|---|
| 30게임·3시장·11분류 무료 검색 | 20 | 990 조사 작업, 605 등록 지역 구분, 6종 링크 |
| 다중 출처 병합·오탐 방지 | 25 | 실제 5발견→3행사·4고유 행사별 출처, 날짜/장소/국가 다르면 분리 |
| 출처 근거·키워드/발견경로 보존 | 20 | 공식/보조/인덱스 각각 URL·파일·발견채널·확인일, 출처 사칭 방어 |
| 실제 제조사 이벤트/경품 실자료 충실도 | 25 | **현재 예시 3건만 증거 확보**, 다른 게임/영화/콜라보 자료 실측 부족 |
| HTTP/CSV/RSS 안전과 무료 운영 | 15 | RSS DTD 비활성, URL 검증, 자동 SNS 수집 금지, HTTP 429 무단 우회 금지 |
| 최신 HEAD Python+Node 회귀/CodeQL·manifest | 10 | 작성된 테스트의 **실제 실행 결과 전까지 미인증** |
| Lenovo Android 태블릿 성능·오프라인·통합 UI | 5 | 실기기 확인 필요 |
| **합계** | **120** | **실증 점수 100 이상 + 필수 승인 게이트 통과 전 HOLD** |

연관 데이터 설계 참고:
- Google Event structured data: https://developers.google.com/search/docs/appearance/structured-data/event
- Google 중복 URL 대표 주소(캐노니컬): https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls
- Meta 플랫폼의 무단 스크래핑 제한 안내: https://www.facebook.com/help/463983701520800

**출시 상태:** GitHub PR #651은 draft에서 코드 보완하고, 테스트/실기기/CodeQL 결과 확인 전 `main` 병합하지 않는다. 중복 통합 자체가 행사의 실재·경품 지급 보증이나 판매가격 증거는 아님.


## V648 요청 정정 — 카테고리가 통합 경계 (2026-10-12)

가장 중요한 원칙: **행사 자료는 행사(EVENT)끼리만, 프로모(PROMO)는 프로모끼리만, 콜라보(COLLAB)·영화(MOVIE)·경품(GIVEAWAY)도 각각 같은 종류끼리만** 중복 통합한다. 키워드로 종류 전체를 합치지 않는다. 한 캠페인이 행사/프로모 둘 다에 기록되어도 각 분류에 별도 카드로 남는다.

- 태블릿 `tcg_event_intelligence_v646.html`: 상위 화면은 **행사 → 프로모 → 대회 → 콜라보 → 영화 → 경품 → 사은품 → 추첨 → 팝업 → 박람회 → 프리릴리즈** 순서의 개별 제목과 목록 섹션으로 구성. 각 섹션에는 **통합된 소식 건수와 고유 출처 URL 건수**, 해당 소식 아래 URL·발견채널·검색키워드·관찰일을 표시.
- Python `tcg_event_intelligence_v644.py`의 분류별 `category_groups`는 11분류마다 `unique_items`, `source_links`, `event_ids`를 따로 계산. 기존 보수적 동일 행사 ID는 **game + region + category + title + start_date + location**로 계속 병합. 날짜/국가/장소가 다르거나 타 유형이면 다른 소식.
- 브라우저 `tcg_event_intelligence_v646.js`에도 `categoryGroups`를 추가하고 분류별 별도 `section`/카드 목록을 실제로 렌더링. 대형 단일 혼합 목록은 제거. 태블릿 검색은 **분류 안에서 항목 찾기**용 필터일 뿐 카테고리 통합 수단이 아니다.
- `test_tcg_event_category_v648.py`: 같은 이름·같은 날을 행사 2출처/프로모 2출처/영화 1출처로 넣으면 **3개 분류별 소식**, 행사 출처 2·프로모 출처 2·영화 출처 1이 되는지 검사. 동일 URL도 이벤트와 프로모 간 합치지 않음; 날짜·장소가 다르면 같은 행사 카테고리 안에서도 별도 유지. 테스트는 작성했으나 최신 HEAD GitHub Actions·Termux 실기기 전체 통과는 별도 확인 필요.
- **이 기능은 무료이고 새 API 키가 불필요**. 출처 링크는 기사 확인을 위한 기록이며 해당 이벤트 내용의 진실성/경품 당첨을 자동 인증하지 않는다.

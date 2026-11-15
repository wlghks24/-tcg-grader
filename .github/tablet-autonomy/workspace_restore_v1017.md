# V1017 태블릿 통합 작업 화면 복구 검토

운영 태블릿의 기존 cd7b40af 통합 화면을 ca85f2fd 기본 실행 경로가 이어받지 못한 회귀를 수정한다. 서버 SHA 일치만으로는 화면 동등성을 입증하지 못했다.

- 기존 카드·BOX 라이브러리, 검색·국가/게임/상품 필터, 전체 메뉴, 원본 사진 연결, 행사/콜라보/영화 화면 및 단일 수집기 연결을 복구한다.
- START의 기존 서버 시작 한 줄을 통합 런타임으로 전환한다. 같은 START를 이용하는 업데이트/부팅/handoff도 동일 화면으로 진입한다. 이전 HEAD를 고정한 별도 설치/실행기는 재도입하지 않는다.
- 기존 정리 trap, watcher, 단일 실행 잠금, 수집 예산 및 등급학습 경계는 유지한다. 이 패치는 추가 학습을 승인하거나 수집 설정을 활성화하지 않는다.
- 최신 검증된 저장 환율 함수를 재사용해 원화를 먼저 표시한다. 오래되거나 잘못된 환율은 환산 보류, 통화 기호만 있는 가격은 원통화 확인 보류로 표시한다.
- 두 health 경로에 로드한 통합 화면/JS 지문을 제공한다. 별도 읽기 전용 검증기는 서버 SHA, 로드한 자산 지문, 실제 제공한 HTML 메뉴와 JS를 함께 확인한다. 기본 HUB 화면은 SHA가 맞아도 HOLD다.
- 시작 전 통합 화면 의존 파일의 manifest 해시/바이트 및 Python 문법을 검사한다. 누락 시 기본 화면으로 조용히 대체하지 않는다.

## 출처와 검토

정확한 복구 원본 cd7b40afcd9bdfadb0987a70847eee1c3a9f08f8, 기준 ca85f2fd2b64f0f9465ddc0190badc92ac33e1fe, 기능 커밋 ba5f53c49c20378923b7d48af1380f31930af6c3. 파일별 원본/후보 지문은 workspace_restore_v1017.json에 기록한다. main 엔트리, 최신 FX/시세 보안, 패치 도구, handoff, index, 행사 갱신 코드는 변경하지 않았다. 별도 검토자가 화면 연결/환율/구형 실행기 위험을 교차검토했고 원화 표기 시험을 작성했다.

## 실제 수행한 검증

- 기존 CI 세대 shard: Python 440개 PASS(복원한 결정론적 시험과 최신 V1014~V1016 포함).
- 기존 단위 시험의 합성 DOM fixture: JavaScript 46개 PASS. 브라우저/화면 렌더링 실행 아님.
- 기존 실행/정리/번들 회귀 Python 16개 PASS.
- 아키텍처 시험 7개 PASS 및 audit PASS.
- 저장소 무결성 guard, static manifest 1858개, 통합 소스 시작 게이트, Bash 문법, Main SELFREFINE --self-test PASS.
- Code Preflight v2: HIGH 0. 과거 archive/Gemini snapshot의 mutable default MEDIUM 1은 본 패치 범위 밖이며 수정하지 않았다. Ruff/Bandit/Gitleaks/actionlint 미설치.

## 남은 검증

현재 후보의 GitHub CI 및 CodeQL 전체 결과를 확인해야 한다. 태블릿 HTTP/실제 화면·터치·카메라·수집 성공은 NOT_RUN이다. HTTP 검증 성공도 실기기 화면 검증으로 승격하지 않는다. 기존 수집 stale 상태, 현재 세션 부팅 supervisor 및 별도 archive watcher 재가동 여부는 실제 적용 후 확인이 필요하다. 어떤 실행 기록이나 관측 시각도 성공처럼 재작성하지 않는다.

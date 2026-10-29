# v0.10.0 검증 결과

- Python 3.12.14/Linux에서 전체 unittest 54개 PASS (신규 구조 분석 12개 포함)
- GUI 모듈 불러오기 및 시작 전 manifest/전체 Python 구문 검사 PASS
- 테스트 로그: VALIDATION_TESTS.log
- 초기에 Tkinter 공유 라이브러리 경로가 누락돼 import가 실패했으나 런타임의 기존 라이브러리 경로 지정 후 재검사 PASS. 새 설치나 테스트 생략 없음.
- 버전 변경으로 달라진 설치 폴더 기대값은 v0100으로 갱신.
- Code Preflight v2: 1차 17개 파일, HIGH/MEDIUM 0. 테스트 미지정·제외 범위로 HOLD. 이는 별도로 수행한 54개 테스트와 구별.
- Ruff/Bandit/Gitleaks/actionlint 미설치: 해당 검증 미실시.
- Windows GUI 실제 조작, TCG 전체 저장소 실측, GitHub CI, Lenovo 실행: NOT_RUN.
- 대상 코드 자동 수정/통합/병합: 미실시. 원본 보존 및 보호 파일 패치 차단 회귀 테스트 포함.

추가된 테스트는 의도적으로 다른 상수의 함수가 중복으로 분류되지 않는지, 중첩 호출 범위, 순환 의존 그래프, 상대 import 오연결 방지, 손상 입력, HTML escaping, 통합 출력, 로컬 Git 브랜치 무변경을 검증합니다.

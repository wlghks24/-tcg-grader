# PC에 설치하는 코드 검토 작업대

이 기능은 기존 V1~최신 이력 감사와 독립적으로 현재 디스크의 작업 폴더를 분석한다. Git이 없는 폴더와 커밋 전 변경도 입력으로 받는다. 모든 GitHub/CodeQL/AI 의미 분석 기능을 복제한 제품은 아니다.

## 설치와 실행

1. Python 3.10 이상과 Tkinter가 있는 Windows PC에서 이 폴더 전체를 준비한다. 기존 이력 감사 기능에는 Git for Windows도 필요하다.
2. `INSTALL_PC.cmd` 실행. 패키지 SHA256SUMS.json과 각 파일의 실제 바이트를 확인하고 `%LOCALAPPDATA%\TCG_PC_Reviewer_<해시>`에 별도 복사한다. 관리자 권한·다운로드·기존 설치 덮어쓰기·자동 예약 등록은 없다. 체크섬은 패키지 내부 일관성 검사이며 서명된 배포자 인증이 아니다.
3. 표시된 설치 폴더의 `실행_PC.bat`로 창을 연다.
4. 코드 원본 폴더와 원본 밖의 보고서 저장 위치를 선택하고 **현재 코드 분석·수정안**을 누른다. 기존 V 구간 검수 버튼은 별도로 유지한다.
5. 로그에 표시된 새 결과 폴더에서 `review.html`과 `review.json`을 연다. `candidates/`는 수정 후보, `patches/`는 검토용 unified diff다. 기존 원본에 자동 적용하지 않는다.

CLI: `py -3 pc_auditor\local_review.py C:\MyCode --out C:\Reviews\new_review`
기본 종료코드 2는 전체 기능 승인 HOLD를 뜻한다. 코드 검사 결과가 없다는 이유로 릴리스를 승인하지 않는다.

## 실제 구현 범위

- Python AST + 컴파일 문법 검증(프로젝트 모듈 import/실행 없음), 빈 함수/NotImplementedError 단서, 동적 실행/shell=True 검토 단서.
- JSON 구문·중복 키·비유한 수, UTF-8 인코딩, 마지막 줄바꿈.
- Python 주석의 작은 영문 사전 4개(teh/recieve/retrun/funtion). 한글 맞춤법·식별자 오타 전체 검사는 아니다.
- 주석 오타/마지막 줄바꿈은 별도 후보로 수정한 뒤 Python AST 동일성 및 내장 규칙을 다시 검사한다. 런타임 의미·도구 지시 주석·미구현 기능의 정답은 사람이 확인해야 한다.
- 크기/파일/전체 바이트/탐색 수 제한, symlink 제외, 검사 중 기존 스캔 파일 변경 시 보고서 게시 중단, 제외/미지원 범위 기록.
- JS/TS/JSX/TSX/YAML은 수집·줄바꿈 검토만 하며 내장 문법 검사가 없음을 coverage_gaps에 남긴다.

## 선택형 로컬 도구와 테스트

- **Ruff**: https://github.com/astral-sh/ruff / https://docs.astral.sh/ruff/configuration/ . MIT 라이선스 프로젝트, 외부 실행 파일을 복사하지 않고 CLI만 연결한다. 설치된 경우 체크박스 또는 `--ruff`로 실행한다. `--isolated --no-cache --no-fix --output-format json --select E9,F`로 복사본만 검사한다. 설치되지 않으면 MISSING, 오류/타임아웃은 ERROR로 남긴다. 앱이 다운로드하거나 패키지를 설치하지 않는다. 실제 PC Ruff 버전과 실행 결과는 보고서에 기록한다.
- **unittest**: 체크박스 또는 `--run-tests`를 명시한 경우에만 원본 스냅샷의 `tests/`를 실행한다. 복사본은 샌드박스가 아니며 테스트 코드는 PC 사용자 권한을 가진다. 타임아웃/실패/0개 테스트/잘린 로그는 PASS가 아니다. 이 테스트는 원본 스냅샷 기준이며 수정 후보의 동작 검증은 NOT_RUN이다.
- Bandit와 codespell은 공식 문서를 조사했으나 이번 배포에는 연결하지 않았다. 별도 호환성·설치 검증 없이 모두 지원한다고 표시하지 않는다.

## 개발 검토 절차

저장소의 tcg-code-review, tcg-test-gap-audit, tcg-supply-chain 및 기존 code-preflight-auto의 원칙을 적용했다. 지침을 실행 가능한 AI 모델로 오인하지 않는다. 새 외부 스킬/AI 서비스/유료 API/클라우드 실행은 도입하지 않았다.

원본 보호 → 실제 실패 재현 → 최소 수정 후보 → 정적 재검사 → 선택형 기능 테스트 → 사람 재검토/현재 HEAD CI 순서다. 자동 병합·태블릿 설치·모델 학습·임의 기능 자동 구현은 없다. 실제 Windows GUI/설치와 실제 Ruff 연동은 이 제작 환경에서 미검증이다.

검증 기록: Python 3.12.14/Linux에서 전체 unittest 114개 PASS(15.836초). 실제 패키지 전체 설치 복사 및 SHA-256 검증 PASS. 이 환경에는 Ruff가 없어 실제 Ruff 실행은 MISSING이며 어댑터의 미설치 경로만 검증했다. Windows 실기기 검증은 별도다.

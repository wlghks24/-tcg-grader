# v0.11.0 로컬 AI 수정안
START_HERE.cmd → 로컬 AI 수정안 생성 → Python 파일 → 설치된 Ollama 모델 이름 → 수정 목표.
PC에서 Ollama 서버와 로컬 모델이 먼저 준비되어야 합니다. 이 ZIP에는 모델이 포함되지 않습니다. 클라우드 모델을 선택하지 마세요. 연결은 127.0.0.1:11434로 고정되며 프록시/리디렉션은 차단합니다.
결과: candidate.py, proposal.patch, AI_REVIEW.json. 원본은 수정하지 않습니다. 문법 검사만 자동 수행하며 행동 테스트는 NOT_RUN으로 표시됩니다. 보호 manifest 파일은 차단됩니다.
실제 Ollama 모델 추론 및 Windows 화면 조작은 이 환경에서 미검증입니다. 후보를 실행하기 전에 패치를 검토해야 합니다.

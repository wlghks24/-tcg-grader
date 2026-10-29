# AI 검토와 GitHub 패치 연결

현재 코드 심층 검사 후 다음 명령으로 검토 요청을 만듭니다.

    python ai_handoff.py 보고서폴더/architecture.json --out AI_REQUEST.json

AI_REQUEST.json은 최대 30개 항목의 근거와 수정 요청을 담습니다. 자동 전송하지 않으므로 공유 전 내용을 확인하세요. 코드 원문은 포함하지 않으며 관련 소스와 review.json의 SHA 근거를 함께 검토해야 합니다. AI에는 재현 테스트, 최소 unified patch, 영향 범위와 미확인 사항을 요구합니다.

이 기능은 AI 검토 인수인계이며 LLM 실행 기능은 아직 아닙니다. API 키나 유료 서비스가 필요하지 않습니다. AI 패치는 별도 Git 브랜치에서 검토하고 현재 HEAD CI를 확인해야 합니다. 원본 자동 적용·자동 병합은 구현하지 않았습니다.

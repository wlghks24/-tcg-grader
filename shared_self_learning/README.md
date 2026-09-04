# Shared SELFREFINE Learning

이 디렉터리는 Main SELFREFINE과 Instagram TCG SELFREFINE이 함께 사용하는 **순수 알고리즘/계약 전용**입니다.

공유 허용:
- error observation 정규화
- domain namespace signature/fingerprint
- priority 계산
- retry bucket 결정 알고리즘
- factual cross-check 비교 알고리즘

공유 금지:
- error ledger
- retry_count history
- cooldown/provider health
- collector registry
- render state
- 학습 결과 파일
- 파일/DB/network I/O
- Main/Instagram runtime import

동일 알고리즘을 사용해도 main: 과 instagram_content: namespace가 붙어 학습 키와 상태는 서로 분리됩니다.

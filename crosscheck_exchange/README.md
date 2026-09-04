# Cross-check Exchange Boundary

이 경로는 Main TCG Grader와 Instagram TCG Content가 **정보를 교차확인하기 위한 데이터 교환 전용 영역**이다.

허용:
- JSON / JSONL 형식의 비실행 데이터
- source_code, source_locator, checked_at_kst, game, entity_type, canonical_key
- 원문 값/통화/등급/언어/variant/출시일/거래시각/검증상태/신뢰도 등 교차검증에 필요한 사실 필드
- 각 도메인이 독립적으로 수집한 결과의 비교
- 동일 canonical_key에 대한 일치/불일치/conflict 판정

금지:
- Python/JavaScript/Shell/배치/실행파일/직렬화 코드 객체를 이 경로로 전달
- 상대 도메인의 모듈 import
- 상대 도메인의 collector/parser/retry/self-healing 코드를 호출
- 오류 ledger, retry_count, cooldown, provider score, 학습 정책을 서로 공유하거나 병합
- 교환 JSON의 문자열을 exec/eval/compile/importlib/runpy 등으로 실행
- 한쪽 도메인의 성공/실패를 다른 쪽 도메인의 수집기 상태로 기록

원칙:
1. Main과 Instagram은 각각 독립적으로 수집한다.
2. 코드와 런타임 상태는 완전히 분리한다.
3. 교차확인은 결과 데이터 레이어에서만 수행한다.
4. 같은 값이라도 양쪽 lineage/source는 각각 유지한다.
5. 충돌값은 평균내지 않고 conflict로 남긴다.
6. 실제 완료거래와 시장참고값은 다른 information_family로 유지한다.
7. 교환 데이터가 없어도 각 도메인은 독립 실행 가능해야 한다.

# Cross-check Exchange Boundary

이 경로는 Main TCG Grader와 Instagram TCG Content가 **사실 정보만 교차검증**하기 위한 데이터 교환 전용 영역입니다.

## 허용
- JSON / JSONL 비실행 데이터
- information_family, canonical_key, value
- source_code / source_locator / checked_at_kst
- currency / language / variant
- verification / confidence
- lineage_key

## 금지
- Python/JavaScript/Shell/배치/직렬화 코드 객체
- 상대 도메인 모듈 import
- collector/parser/retry/self-healing 호출
- retry_count / cooldown / provider score / provider health
- error ledger / learning state / render state / collector state
- 교환 문자열을 exec/eval/compile/importlib/runpy로 실행
- 한쪽 verified 상태를 상대쪽 verified로 자동 승격

## 실제 흐름
1. Main은 main_crosscheck_export.py로 자체 결과를 passive JSON으로 내보냅니다.
2. Instagram은 python -m instagram_tcg_content.crosscheck_export로 자체 결과를 별도로 내보냅니다.
3. selfrefine_crosscheck_gate.py가 동일 information_family + canonical_key + currency/language/variant만 비교합니다.
4. 값이 같으면 agree, 다르면 conflict로 남깁니다.
5. conflict는 평균내지 않습니다.
6. 각 도메인의 verification/lineage/state는 그대로 유지됩니다.

런타임 교환 파일은 Git에 커밋하지 않으며 .gitignore로 제외합니다. 교환 데이터가 없어도 두 도메인은 독립 실행됩니다.

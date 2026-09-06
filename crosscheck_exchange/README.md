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

## 운영 브리지
실제 수집 결과를 교차확인할 때는 `python crosscheck_runtime_bridge.py --main-input <main.json> --instagram-input <instagram.json>`를 사용합니다.
이 브리지는 정확히 8개 factual type(`card_price`, `release`, `rerelease`, `promo`, `event`, `movie_bonus`, `completed_sale`, `market_reference`)만 허용하고, 양쪽 입력이 모두 존재할 때만 runtime snapshot을 만든 뒤 schema 검증과 conflict 비교를 수행합니다.
한쪽 입력이 비어 있으면 빈 snapshot을 만들어 PASS 처리하지 않고 `snapshot_missing` / `operational_ready=false`로 종료합니다. conflict는 평균내거나 자동 승격하지 않고 `reverification_required`로 남깁니다.

런타임 교환 파일은 Git에 커밋하지 않으며 .gitignore로 제외합니다. 교환 데이터가 없어도 두 도메인은 독립 실행됩니다.

## Persisted factual snapshot runtime
실제 수집 결과의 시스템 간 교차확인은 두 단계로 분리됩니다.

- 각 도메인은 자기 소유 factual row만 `TCG_CROSSCHECK/MARKET_ANALYSIS/factual_snapshot.json` 또는 `TCG_CROSSCHECK/IG_CARDINFO/factual_snapshot.json`에 `status=finalized`로 저장합니다. 저장 시 정확히 8개 factual type만 허용하며 verified row가 하나도 없으면 기존 finalized snapshot을 빈 값으로 덮어쓰지 않습니다.
- 중립 control plane `crosscheck_persisted_runtime.py`가 두 persisted snapshot의 namespace/status/finalized_at/validation/provenance를 검증한 뒤 verified row만 `crosscheck_runtime_bridge.py`로 전달합니다.
- 한쪽 snapshot이 없거나 building/empty이면 기존 runtime-main/runtime-instagram 파일을 삭제해 stale 데이터가 다음 감사에서 재사용되지 않게 하고 `operational_ready=false`로 남깁니다.
- 양쪽 finalized verified snapshot이 실제 존재할 때만 runtime exchange를 생성하고 `crosschecked`로 처리합니다. conflict는 자동 평균/승격하지 않고 reverification 대상으로 유지합니다.

도메인 exporter는 실제 factual input을 받은 경우에만 persisted snapshot을 쓸 수 있습니다. 예: `python -m instagram_tcg_content.crosscheck_export --input <verified_rows.json> --persisted-output TCG_CROSSCHECK/IG_CARDINFO/factual_snapshot.json`. 입력이 없거나 verified row가 없으면 snapshot을 생성/갱신하지 않습니다.

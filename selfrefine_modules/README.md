# SELFREFINE module separation

현재 TCG Grader의 SELFREFINE 코드를 다음 4개 책임으로 별도 관리합니다.

| 모듈 | 책임 | 상태 분리 |
| --- | --- | --- |
| `grading_vision` | 1→4→8 카드 등급 비전검사, 검증 등급 기반 보정 | `vision_calibration.json` |
| `collection` | 가격/행사/출시/등급사진 수집, 공급자 상태 학습 | `MAIN_SELFREFINE_PROVIDER_STATE.json` |
| `repair_security` | 오류 격리, 검증된 자동수정, 롤백, 해결결과 학습 | repair/quarantine/learning/retry 상태 |
| `orchestration` | 위 모듈들의 실행 순서와 정책/무결성 검사 연결 | `MAIN_SELFREFINE_ERROR_LEDGER.json` |

## 원칙

1. 한 소스/상태 파일은 한 모듈만 소유합니다.
2. 다른 모듈의 상태 파일을 직접 합치거나 평균내지 않습니다.
3. 오케스트레이션 계층은 비전/수집/수정 엔진의 내부 상태를 소유하지 않습니다.
4. 공통 순수 알고리즘은 기존 `shared_self_learning/`만 사용합니다.
5. `test_selfrefine_module_registry_v18.py`가 파일 누락, 중복 소유, 상태 충돌을 fail-closed로 차단합니다.
6. 기존 루트 파일 경로는 태블릿/Windows/GitHub Pages 호환성을 위해 유지하고, 신규 개발은 이 레지스트리의 소유권에 따라 수정합니다.

실행:

```bash
python -m selfrefine_modules.registry
python -m unittest -v test_selfrefine_module_registry_v18.py
```

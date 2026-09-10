# Instagram TCG Content Domain

이 디렉터리는 **인스타 카드정보** 전용 도메인입니다. Pokémon / ONE PIECE / NARUTO의 KR/EN 카드정보를 수집·검증하고, 하나의 canonical 예약에서 평상시 수집과 주 1회 최종 제작을 분기합니다.

## Single canonical schedule (KST)

- **활성 인스타 카드정보 예약은 하나만 유지**합니다.
- 예약은 **매시간 정각** 실행합니다.
- **월요일 19:00 KST만 `WEEKLY_PRODUCTION`** 입니다.
- 그 외 모든 정각은 `COLLECTION_VERIFY_REFINE_ONLY`이며 자료수집·교차검증·delta 반영·오류진단·안전한 최소 수정·품질 보완만 수행합니다.
- 월요일 19:00 외에는 최종 PNG 렌더와 `VERIFIED_DELIVERY`를 금지합니다.
- 과거 10:30 일일 baseline / 22:30 수정판 / 매시 :30 라우터는 **legacy history**이며 현재 스케줄 SSOT가 아닙니다.

현재 스케줄/분류 SSOT는 `single_task_router.py`입니다. 기존 `production_state.py`, `production_recovery_policy.py`, `automation_state_guard.py`의 과거 스케줄 표현은 과거 상태 읽기 호환용으로만 취급하고, 현재 실행은 `weekly_production_state.py`, `weekly_recovery_policy.py`, `single_task_router.py`의 가드를 먼저 통과해야 합니다.

## Collection and verification

수집 범위는 release, rerelease/reprint, promo, event, movie bonus, festival, card news, completed sale, market reference, FX입니다. 공식 사실은 official primary를 필수로 하고, discovery/repost/snippet 단독값은 verified fact로 승격하지 않습니다. completed sale과 market reference는 별도 근거 체계를 유지합니다.

행사·발매·재발매·영화·프로모·축제는 종료일까지 현행 영역에 유지하고, 종료 후 5일차까지 계속 노출하며, **6일차부터 archive**로 이동합니다.

KR/EN 6개 출력 매트릭스는 Pokémon KR/EN, ONE PIECE KR/EN, NARUTO KR/EN입니다. 가격/거래 근거가 부족하면 해당 시장 섹션만 보류하고 검증된 일반 카드정보를 폐기하지 않습니다.

## Production hard gates

월요일 19:00 제작은 누적 verified state를 읽은 뒤 마지막 delta collection 및 교차검증을 수행합니다. finalization 전에는 raw Observation 그룹을 `source_verification_engine` 계열로 직접 검증해야 하며, AI 점수나 외부에서 만든 결과는 사실 검증 권한이 없습니다.

최종 산출물은 1080x1350 PNG 6개이며 locked master를 변경하지 않습니다. 모든 파일의 reopen/decode/size, 서로 다른 SHA-256, attachment/delivery reference를 확인한 뒤에만 `VERIFIED_DELIVERY`를 사용합니다.

## Isolation and reliability

Main 카드시세분석, 애니정보, 릴스, 주식 프로젝트의 factual state·learning·automation state를 섞지 않습니다. 오류는 직접 증거가 있을 때만 root cause로 확정하며, 증거가 없으면 unresolved로 유지합니다. runtime failure는 scheduler 자체를 disable/pause/reschedule하는 이유가 아닙니다.

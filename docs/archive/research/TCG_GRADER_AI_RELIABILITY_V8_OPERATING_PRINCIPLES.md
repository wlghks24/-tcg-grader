# 카드시세분석 AI 신뢰성 v8 운영원칙

## 고정 연결

- 프로젝트: `tcg_grader`
- 기존 예약 ID: `6a9b878f35bc8191963b8685566709c4`
- 저장소 SSOT: `wlghks24/-tcg-grader`의 `main`
- 실제 서버 진입점: `tcg_updater_v135.py:main`
- 카드시세분석 전용 패키지: `tcg_reliability/ai_reliability_v8`
- 상태 경로: 기본 `.tcg_reliability_state`; project/task 해시 네임스페이스로 분리

`instagram_card`, `anime`, `reels`, `stock`의 설정·상태·학습·예약 ID를 가져오지 않는다. 루트의 기존 `ai_reliability_v8`은 `instagram_card` 전용이므로 카드시세분석에서 import하거나 덮어쓰지 않는다.

## 변경 순서와 활성화 게이트

`inventory → binding → backup → read_only_plan → additive_install → wire_one_entrypoint → targeted_tests → full_regression → actual_output_validation → activate`

각 단계는 동일 project/task_id, 시간대 포함 시각, 성공 증거와 필요한 SHA-256을 남긴다. 앞 9개 단계의 영수증이 모두 통과해 `activation_authorized=True`가 되기 전에는 기존 예약을 활성화하지 않는다. 새 예약·복제본·watchdog을 만들지 않는다.

## 신경망·학습 원칙

- 실제 독립 라벨이 1,000개 미만이면 새 신경망을 학습하거나 승격하지 않고 기존 모델을 유지한다.
- 1,000개 이상일 때만 은닉 크기 4·8·12와 각 3개 고정 시드를 비교한다.
- 시간순 train/tune/calibration/final-test를 분리하며 tune 이외 구간을 구조 선택에 사용하지 않는다.
- 출처 소유자 최소 3개, 단일 소유자 지배율 70% 이하, 중복 origin 차단을 요구한다.
- NaN/Infinity, 모델 손상, 특징 순서·차원 불일치, scope·권한 불일치, Brier/ECE/고오판 Wilson 상한, 특징 드리프트를 검사한다.
- 합성 데이터와 AI 자체 판단은 운영 정답 라벨로 사용하지 않는다. 모델은 검토 우선순위만 제안하며 사실 검증 권한을 갖지 않는다.

## 코드 수정·복원 원칙

- 수정 전에 코드지도에서 대표 진입점, 영향 파일, 추천 테스트와 검증 수준을 찾는다.
- 허용 파일, 변경량, AST 위험 호출, syntax, targeted regression, holdout, post-apply, 전체 회귀를 모두 확인한다.
- 예약 변경, 셸/프로세스 실행 추가, 우회 수집, 자동 모델 승격, 자동 코드 생성·적용은 허용하지 않는다.
- 실패한 후보는 원본 바이트로 복원하고 실패 증거와 해시를 보존한다.
- 기존 등급·시세·기기별 기능과 학습 기록은 덮어쓰지 않는다.

## 검증·보고 원칙

- 첨부 119개 테스트, 코드지도 영향 테스트, 기존 프로젝트 회귀와 실제 HTTP/UI/등급 결과를 분리 보고한다.
- 결합 테스트나 CI PASS를 실제 예약 실행 성공으로 대체하지 않는다.
- 실제 카드 사진과 독립 정답 라벨이 없으면 등급 정확도 개선·신경망 학습 완료를 주장하지 않는다.
- 예약 첫 실행 결과가 없으면 `SCHEDULED_RUN_UNVERIFIED`로 남긴다.
- 단일-process 전체 테스트의 기존 전역상태 오염처럼 원본에서도 재현되는 문제는 신규 회귀와 구분하되 숨기지 않는다.


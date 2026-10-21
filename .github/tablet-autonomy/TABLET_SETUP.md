# 태블릿 자동 실행 설정과 검증

이 문서는 기존 `main` 진입점과 `TABLET_SCHEDULED_UPDATE.sh`만 사용한다.
GPT 예약은 태블릿의 Termux 프로세스를 원격 실행하지 않는다.

## 태블릿에서 한 번 실행

기존에 `bash main`을 실행하던 프로젝트 폴더에서:

```bash
bash main update-install
bash main update-status
```

`SCHEDULE=installed`, `BOOT_LOOP=running:<PID>`, `TERMUX_BOOT=detected`를 각각 확인한다.
설치 스크립트 성공만으로 재부팅 후 실행 성공이라고 판단하지 않는다.
`TERMUX_BOOT=not-detected` 또는 `unknown`이면 재부팅 자동 실행은 보류다.
Termux:Boot 설치 및 Android의 백그라운드 실행 허용 상태는 태블릿에서 확인해야 한다.

## 자동 실행 범위

- 기존 루프가 매일 23:00 KST에 최신 main 확인 및 한 번의 제한된 자율 진단/학습 사이클을 실행한다.
- 자료·자원·검증 근거가 부족한 학습은 보류한다. 자기점수를 정답으로 만들지 않는다.
- 로컬 변경은 보호한다. PR의 패치를 설치하려고 staged 파일을 삭제하거나 강제 초기화하지 않는다.
- PR #768은 CI와 실기기 확인 전까지 배포 후보이며, 이 문서는 병합 또는 설치 완료 영수증이 아니다.
- 부팅 스크립트는 예약 루프를 시작한다. 웹 서버가 재부팅 후 자동 시작된다고 확대 해석하지 않는다.

## 실제 완료 증거

재부팅 후 위 상태를 다시 조회하고 `BOOT_LOOP_HEARTBEAT_AT`와 실제 예약 실행 기록을 확인한다.
실행 시각 뒤 `AUTONOMY_RESULT`, 해당 로그, 설치 SHA를 함께 검토한다.
`AUTONOMY_RESULT=OK`도 모든 모델 학습 또는 모든 기능의 개선 완료를 뜻하지 않는다.
코드/CI 검증, 태블릿 설치, 부팅 자동 실행, 실제 예약 실행은 별도 상태로 기록한다.

이 패치 검증은 코드 해시·커밋 이력과 임시 환경의 설치 동작에 한정한다.
실기기 렉·배터리·메모리 수치는 관측 전까지 미검증이다.

## 예약 결과 구분 (V643 후보)

`AUTONOMY_RESULT=HOLD`는 종료 코드 2와 최종 V400 JSON의 알려진 보류 상태, 실행 차단 게이트, 미실행 표시가 일치할 때만 기록된다. 인자 오류·예외·파손/누락 로그·알 수 없는 상태는 계속 FAILED다. HOLD에서도 원래 종료 코드 2를 유지하며, 학습 조건이나 원본 데이터를 변경하지 않는다. 이 구분은 최초 학습 근거 생성이나 태블릿 설치를 완료한 증거가 아니다.

## 실제 학습자료와 자율판단 기록의 구분 (V644 후보)

V387의 local/peer verified outcomes 0건은 query/job 신경망의 검증 라벨 수를 의미하지 않는다. `auto_update_all.run_all()`은 기존 수집 경로에서 작업 신경망의 검증·학습 조건을 별도로 확인한다. 실제 라벨 수와 활성 상태는 `bash main learn-status`에서 읽는다. 수정된 `bash main learn`은 상위 실행이 보류돼도 이 상태를 표시하며, 원래 보류/오류 종료 코드를 유지한다.

기존 매일23시 실행 뒤에도 `learn-status`를 최대10초 동안 읽어 별도 JSON으로 기록한다. `bash main update-status`의 `LEARNING_LAST_CHECK`, `LEARNING_SOURCE_SHA`, `LEARNING_STATUS`, `LEARNING_STATUS_LOG`로 이번 기록 여부와 경로를 확인한다. 조회 실패/timeout 명령 부재는 UNAVAILABLE이며 과거 기록을 최신 성공으로 표시하지 않는다. 조회는 학습·임계값 변경·검증자료 생성을 수행하지 않는다.

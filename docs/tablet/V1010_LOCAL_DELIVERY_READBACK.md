# Lenovo 태블릿 카드 AI V1010 — 설치/실행 한 화면 증빙

기존 GitHub main → Termux 매일 23:00 KST 업데이트 체계를 그대로 두고 태블릿에서 로컬 코드·서버·예약 버전의 상태를 확인하는 **읽기 전용 명령**을 추가합니다.

## 기존 Termux에서 확인

별도 앱·APK·데몬·예약 없이, 이 변경이 보호된 main에 정식 병합되고 기존 태블릿이 수신한 후 다음 명령을 사용할 수 있습니다.

~~~bash
bash main delivery-status
bash main delivery-status --json
bash main delivery-status --require-ready
~~~

--require-ready는 로컬 증빙이 부족하면 종료코드 2를 반환합니다. READY_FOR_PHYSICAL_CHECK도 설치 완료, 재부팅 완료, PWA 화면 확인, 카드 스캔 정확도, 시세 정확도를 뜻하지 않습니다.

## 표시하는 현황

- 코드 업데이트: LOCAL_MAIN_CHECK_VERIFIED / MAIN_UPDATE_HOLD / MAIN_UPDATE_UNVERIFIED
- 실제 실행 서버: RUNNING_SHA_VERIFIED_LOCAL_HTTP / RUNNING_SHA_MISMATCH / RUNNING_SHA_UNVERIFIED
- 예약 루프: LOOP_RUNNING_LOCALLY / LOOP_NOT_VERIFIED 및 기존 Termux:Boot 스크립트 존재 여부
- Git 디스크 HEAD, 업데이트 영수증의 REMOTE_SHA, 로컬 origin/main, 실행 서버 SHA를 서로 독립적으로 표시
- 한글 요약 및 기계 판독용 JSON 모두 민감한 환경변수/토큰이나 전체 원본 로그는 포함하지 않음

## 보안·역사 보호

- V1005의 tablet_runtime_probe.py, execution/tablet_delivery_status_v1005.py, 선행 불변 증빙과 기존 테스트를 수정하지 않음.
- 기존 probe를 읽기 전용으로 호출하며, LAN 스캔·실시간 GitHub fetch·소스 수정·서버 재시작·모델 및 학습 데이터 변경 없음. 로컬 127.0.0.1:8765 health API만 조회.
- 기존 bash main update-now, update-status, 매일 23:00 예약 및 장애복구 로직에는 영향 없음.
- 현장 설치·기기 UI·재부팅의 참거짓은 GitHub CI로 알 수 없으므로 physical_tablet_verified, reboot_verified, pwa_visual_verified, live_github_main_verified, device_restart_authorized는 항상 false.
- 이 후속 PR에서 main 병합 권한을 부여하지 않음. 보호 규칙과 사람의 검토 및 실제 Lenovo 현장 검증은 별도.

## CI

기존 V1005 회귀검사 + V1010 신규 14개 부정/양성 검사, 실제 셸 문법, 로컬 실행, source SHA-256과 Git 후보 계보를 검증합니다.

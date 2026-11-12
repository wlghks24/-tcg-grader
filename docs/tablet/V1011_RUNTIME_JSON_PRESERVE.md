# Lenovo V1011 학습 JSON 원본 보존 · 안전 코드 업데이트 후보

상태: **검토용 후속 패치. main 미병합, 태블릿 설치/재시작 미승인.**
기준: V1010 PR #1139 HEAD `4ee8f6398e122dd7208bf2d5ecfaaa3d82c1b76c`. 변경 후보 `e68a8220d53f8b0d923cd425de9fb45d04fda82d`.

## 현장 배경

기존 운영 `$HOME/-tcg-grader`는 `cd7b40af` detached HEAD이며 GitHub main과 이력이 분기됨. 추적 JSON 30개 변경 및 Git 무시/미추적 파일 5,455개(약 301 MiB)가 현장에 존재. 사용자가 변경 JSON 30/30, Git bundle, 추가 파일 5455/5455를 로컬에 보존하고 해시 검증함. 이로써 일관된 포인트 인 타임 복구나 물리적 설치가 검증된 것은 아님.

## 변경

`ANDROID_UPDATE_AND_START.sh`의 **호출 경로**에서 기존 `backup_and_normalize_runtime`(추적 학습 JSON Git 기준값으로 복원)을 사용하지 않음.
- 로컬 브랜치가 `main`이 아니면 기존과 같이 HOLD.
- 현재 HEAD → 신규 main이 fast-forward 불가하면 기존 이력을 보존하고 HOLD.
- 로컬에서 변경된 추적 JSON이 있다면, 신규 main이 해당 파일을 바꾸지 않을 때만 코드 fast-forward를 시도.
- JSON이 원격에서 변경되거나 심볼릭 링크이면 HOLD. 코드 변경도 Git checkout에서 충돌하면 안전 중단.
- **자동 마이그레이션/데이터 덮어쓰기 금지**. 복원본을 사용한 임의의 자동 복원도 없음.
- 기존 스크립트에 남아 있는 `backup_and_normalize_runtime` 함수는 역사적 소스 계약 보존을 위해 제거하지 않았지만 정상 업데이트 경로에서 호출하지 않음.

## 테스트

`python -m unittest -v execution.tests.test_tablet_runtime_preserve_ff_v1011`

별도 임시 Git 저장소에서 실제 `git fetch`, `git merge --ff-only`을 사용해 코드만 변경할 때 추적 학습 JSON이 바이트 단위로 그대로 남는지 확인. 새 main에서 JSON 변경, detached HEAD, 이력 분기, 수동 소스 수정, 심볼릭 링크는 자동 업데이트 차단.

## 주의/후속 게이트

본 수정은 **기존 운영 detached/diverged checkout을 자동으로 수리하지 않음**. `~/tcg-grader-main`은 별도 clean repo이지만 운영 서버/23시 스케줄 ROOT가 아니므로 임의로 바꾸지 않음. 운영 활성 서버·학습·사진/모델 연결, 스냅샷 원자성, 외부 저장소 2차 백업, 기존 #1134→#1139→V1011 보호규칙/병합, 실제 Lenovo 화면·서버 SHA 확인이 뒤따라야 함.

이 변경은 자료 보존이 안전하다고 확인된 일반 코드-only fast-forward를 가능하게 만드는 **후보**다.

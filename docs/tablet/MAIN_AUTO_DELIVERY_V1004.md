# 태블릿 GitHub main 자동 배포 경로 확인 (V1004)

**새로운 설치기가 아닙니다. 별도의 ZIP, APK, 수동 다운로드를 요구하지 않습니다.**

현재 활성 구조는 Lenovo/Termux에서 `TABLET_SCHEDULED_UPDATE.sh`가 매일
23:00 KST 공식 GitHub `main`을 확인하고, 기존 안전 업데이터를 사용해
fast-forward 가능한 코드만 반영하는 방식입니다. 기존 자동 감시가 설정된
기기는 `execution.tablet_local_automation`을 통해 실제 서버 SHA를 다시
확인하고 필요한 경우 기존 검증된 런타임으로 교체합니다.

새로운 GitHub Action `Tablet Main Auto-Pickup Source Guard`는 매 main push와
관련 PR에서 **소스 코드의 자동 갱신 계약**만 확인하고 JSON 증빙을 생성합니다.
GitHub Actions는 태블릿의 Termux 프로세스에 접근할 수 없으므로
`physical_tablet_verified=false`, `installed_sha=null`을 유지합니다.
보고서의 `code_ready_on_main=true`는 **실기기 설치 성공이 아닙니다**.

실제 성공 판정에는 태블릿의 기존 `bash main update-status`,
`bash main auto-status`, `python tablet_runtime_probe.py --require-health
--require-runtime-contract`에서 실행된 SHA와 GitHub main SHA의 일치,
서버 HTTP health, 이후 재부팅 점검이 필요합니다. 기존 자료, 카드 사진,
정답 라벨, 보정값, 로컬 모델은 GitHub CI에서 변경하지 않습니다.

작업 범위에서 V1004 별도 설치 PR #1122는 사용자 요청에 따라 미병합 종료하였고
본 검증은 기존 main 코드/부팅/자동 복구 루틴을 대체하지 않습니다.

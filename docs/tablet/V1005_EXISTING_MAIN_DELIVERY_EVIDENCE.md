# V1005 기존 main 자동 반영 증빙 (별도 설치 없음)

이 패치는 기존 Lenovo/Termux 설치 환경과 `bash main`/23:00 KST 업데이트 예약을 그대로 이용합니다. 추가 ZIP/APK/데몬/예약을 설치하지 않으며, 사진·수집 데이터·라벨·학습 모델·기존 사용자 소스 변경을 수정하지 않습니다.

`tablet_runtime_probe.py`의 기존 응답에 `delivery` 필드가 자동 포함됩니다. 기존 `execution.tablet_local_automation`이 서버를 검사할 때도 이 판정을 조회하지만, 그것만으로 실기기 부팅 검증을 완료한 것으로 간주하지 않습니다.

- `code_update_status`: 공식 origin/main 로컬 참조, 디스크 HEAD, 26시간 이내의 기존 예약 영수증이 정확히 일치할 때만 `LOCAL_MAIN_CHECK_VERIFIED`; 원격 네트워크의 최신 상태를 실시간으로 증명하는 이름이 아님
- `runtime_status`: 현재 로컬 `127.0.0.1:8765/api/v135-health`에서 실행 SHA와 디스크 HEAD가 일치할 때 `RUNNING_SHA_VERIFIED_LOCAL_HTTP`; 오래된 서버는 `RUNNING_SHA_MISMATCH`
- `scheduler_status`: 기존 23시 boot-loop의 기록 PID, `/proc` 소유자/명령행, 버전 및 heartbeat를 일치 검증할 때 `LOOP_RUNNING_LOCALLY`
- `boot_script_present`: Termux:Boot 스크립트 파일 존재. 실제 재부팅 자동 실행 증거는 아님
- `reboot_verified`, `physical_tablet_verified`: 기본적으로 `false`; 원격 GitHub CI나 HTTP 성공으로 실제 재부팅/터치/UI 성능을 단정하지 않음

기존 태블릿에서 추가 설치 없이 진단할 때는 프로젝트 폴더에서 `python tablet_runtime_probe.py --require-health --require-runtime-contract`를 이용합니다. 반환 JSON의 `delivery` 필드를 확인하세요. 기존 `bash main update-status`, `bash main auto-status`도 계속 지원됩니다.

`ready_for_device_readback=true`는 현지 운영 증빙의 조합일 뿐 실제 Lenovo 재부팅/브라우저 PWA/카드 스캔 성공을 뜻하지 않습니다. CI에서 물리적인 태블릿을 원격 제어하지 않습니다. 구동 실패면 기존 자동 업데이트 프로그램의 데이터 보존·fail-closed 동작을 유지합니다.

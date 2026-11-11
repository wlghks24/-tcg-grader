# 기존 GitHub main → Lenovo 자동 반영 검증 V1005

별도 ZIP·APK·설치 앱·데몬·새 예약을 만들지 않습니다. 기존 Termux의 23:00 KST 안전 업데이트와 런타임 감시를 유지합니다.

기존 `tablet_runtime_probe.py` 응답에 `delivery` 필드가 자동 포함됩니다. 기존 자동 감시가 런타임 probe를 조회할 때도 동일한 판정을 사용하되 기존 실행/업데이트 코드를 바꾸지 않습니다.

- `code_update_status`: 공식 origin/main 로컬 참조, 디스크 HEAD, 26시간 이내의 예약 업데이트 영수증이 일치하는 경우에만 `LOCAL_MAIN_CHECK_VERIFIED`; GitHub 최신 원격 상태가 실시간 확인되었다는 주장은 아닙니다.
- `runtime_status`: 로컬 HTTP 실행 SHA와 디스크 HEAD가 검증되어 일치하면 `RUNNING_SHA_VERIFIED_LOCAL_HTTP`, 구버전 실행 시 `RUNNING_SHA_MISMATCH`.
- `scheduler_status`: 이전 설치된 boot-loop의 실제 PID 소유자, 실행 인자, 버전, 기존 heartbeat 검사 후 `LOOP_RUNNING_LOCALLY` 여부 보고.
- `boot_script_present`: Termux:Boot 스크립트 존재 여부. 태블릿 재부팅 성공 증거는 아닙니다.
- `physical_tablet_verified`, `reboot_verified`: 항상 false. PWA/카드 스캔 실제 시험은 별도 증거가 필요합니다.

기존 태블릿 프로젝트에서 추가 설치 없이 다음의 기존 명령만 사용합니다.

```bash
bash main update-status
bash main auto-status
python tablet_runtime_probe.py --require-health --require-runtime-contract
```

세 번째 명령의 JSON `delivery` 항목은 코드 수신·실행 버전·예약 루프를 독립적으로 보여줍니다. 실패 시 사진·라벨·모델·사용자 코드 변경은 그대로 보존합니다.

`ready_for_device_readback=true`는 실제 기기에서 최종 브라우저/재부팅 검사를 진행할 수 있다는 뜻일 뿐, 해당 검사의 완료를 뜻하지 않습니다. GitHub CI로 태블릿 설치 완료라고 단정하지 않습니다.

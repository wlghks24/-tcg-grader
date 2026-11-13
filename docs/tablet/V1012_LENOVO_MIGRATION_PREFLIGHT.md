# Lenovo V1012 백업·분기 이력 사전검증 (읽기 전용)

**상태:** PR 검토용. GitHub main 및 Lenovo 운영 폴더 미변경. 데이터 복원·설치·원격 실행 금지.

## 배경

운영 repo는 `$HOME/-tcg-grader`, HEAD `cd7b40af` detached이며 공식 main과 diverged. 태블릿 내부 `$HOME/tcg-preserve-20261112-232258`에 추적 변경 JSON 30개, Git bundle(28,525 objects/27 refs), 추가 5,455개(약 301 MiB) 별도 보존/해시 검증 보고됨. 외부 장치 2차 백업 미확인.

## 독립 명령 (정식 main 반영 후에만 실행)

```sh
python -m execution.tablet_migration_preflight_v1012 \
  --root "$HOME/-tcg-grader" \
  --backup "$HOME/tcg-preserve-20261112-232258" \
  --extra "$HOME/tcg-preserve-20261112-232258/local-extra-20261112-234739"
```

위 명령은 변경된 JSON 30개 SHA256SUMS, Git bundle SHA256/verify/HEAD, 추가 5,455개 SHA256/bytes/manifest, 로컬 Git 브랜치/캐시된 origin/main 계보를 읽기 전용으로 확인. 사진·토큰·원본 파일명 출력 없음. `--require-ready`는 이 버전에서 **항상** HOLD 종료코드 2를 반환하도록 fail-closed 구성.

## 한계 및 보존 규칙

- GitHub 최신 refs를 fetch하지 않음. origin/main은 **로컬 캐시**일 뿐임.
- 실기기 자료 동시점(quiesced) 스냅샷, 다른 저장장치 복구본, 데이터 restore 테스트, PWA 실행 확인 모두 미완료.
- 기존 운영 Detached HEAD/분기 이력은 사전검사로 자동 복구되지 않음.
- 운영 서버·23시 예약 루프·카드 사진·학습 모델·기존 Git refs/백업은 변경하지 않음.
- PR #1134 → #1139 → #1142 → V1012 보호된 검토·병합 순서 엄수. `git reset --hard`, 강제 checkout/삭제 등 금지.

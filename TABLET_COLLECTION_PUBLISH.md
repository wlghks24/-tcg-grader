# 태블릿 Termux 통합 실행 및 수집 전송

이 저장소는 태블릿에서 `main` 하나를 기준 진입점으로 사용합니다.

## 기본 실행

```sh
cd ~/-tcg-grader
bash main
```

`bash main`은 기존 Android 안전 업데이터를 사용해 공식 GitHub `main`을 확인하고, 새 원격 빌드를 임시 worktree에서 검증한 뒤 fast-forward 가능한 경우에만 갱신하고 서버를 시작합니다. 기기 로컬 학습자료·사진은 기존 Android 보존 정책을 그대로 따릅니다.

## 통합 명령

```sh
bash main collect
bash main publish
bash main verify
bash main recover
```

- `collect`: 공개 TCG 자료를 기존 수집 사이클로 수집한 뒤 Static Data Publish, Collection Verification(`--fail-on-degraded`), 감정업체 계약검증을 실행합니다. 원격 업로드는 하지 않습니다.
- `publish`: 반드시 최신 `main`에서만 동작합니다. 검증된 공개 JSON 17개와 SHA-256 수집 영수증만 별도 자료 브랜치에 커밋하고 PR을 생성합니다.
- `verify`: 현재 태블릿 빌드의 최종 검증을 실행합니다.
- `recover`: 오래된 Android 업데이터 복구 경로를 실행합니다.

## 처음 한 번 필요한 도구

```sh
pkg install git python gh
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
```

`publish`에만 GitHub CLI 인증이 필요합니다. 토큰이나 인증값을 채팅 또는 저장소에 넣지 않습니다.

## 수집 안전 경계

수집은 운영 폴더에서 직접 코드를 바꾸지 않고 `~/.local/state/tcg-grader/collection-runs/` 아래 별도 git worktree에서 실행합니다. 각 실행의 `collection.log`가 보존됩니다.

업로드 허용 대상은 다음 공개 JSON 17개와 `tablet_collection_receipt.json`뿐입니다. 코드, 개인 사진, 인증키, 로컬 학습 폴더는 자료 PR에 포함될 수 없습니다.

영수증은 저장소 ID, 기준 `main` SHA, 수집 시각, 각 공개 JSON의 SHA-256을 기록합니다. symlink, 누락 파일, 20MB 초과 파일, JSON 파싱 실패, 커밋 이후 변조, 15분 초과 영수증, 수집 중 `main` 변경은 모두 전송을 중단합니다.

403/429 우회, 비승인 호스트 허용, 테스트/allowlist 완화는 하지 않습니다. 필수 외부 출처가 degraded 상태이면 `--fail-on-degraded`에 의해 자료 PR 생성을 중단하고 실행 로그와 결과만 기기에 보존합니다.

## 일반적인 태블릿 사용 순서

서버 사용은:

```sh
cd ~/-tcg-grader
bash main
```

업로드 없이 수집 검증은:

```sh
bash main collect
```

검증된 태블릿 수집 결과를 GitHub `main` 반영용 PR로 보내려면:

```sh
bash main publish
```

`publish` 실행 시 현재 HEAD가 원격 최신 `main`과 다르면 자동으로 중단됩니다. 먼저 `bash main`으로 최신 빌드를 적용한 뒤 다시 실행하세요.

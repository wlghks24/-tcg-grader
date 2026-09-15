# 태블릿 수집 결과를 main에 보내기

이 기능이 main에 병합된 뒤 Termux의 저장소 폴더에서 사용합니다.
현재 코드 수정 PR의 필수 검증/병합 조건은 유지합니다.

처음 한 번 GitHub CLI를 설치하고 본인 계정을 연결합니다.

```sh
pkg install git python gh
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
```

저장소의 requirements.txt 의존성이 설치된 기존 태블릿 환경에서:

```sh
git switch main
git pull --ff-only origin main
bash TABLET_COLLECT_AND_SEND.sh
```

운영 중인 폴더를 수정하지 않고 별도 git worktree에서 동일한 8단계 수집기를 실행합니다.
결과는 Termux 홈의 `.local/state/tcg-grader/collection-runs/`에 보존하며 각 실행 폴더의 `collection.log`에 수집 표준출력과 오류를 기록합니다.
전송 전 산출물·영수증이 실제 커밋과 일치하는지도 확인합니다.
기존 최신 main의 공개 자료를 기준으로 시작하며 개인 사진/인증키/학습 폴더는 가져오거나 업로드하지 않습니다.
서버의 로컬 미반영 코드나 개인 사진 수집을 포함하려면 별도 검토가 필요합니다.

Static Data Publish와 Collection Verification(--fail-on-degraded), 감정업체 계약 검증을 모두 통과해야 자료 PR을 생성합니다.
업로드 파일은 기존 static refresh의 공개 JSON 17개 및 수집 영수증뿐입니다.
GitHub에서는 제출된 자료의 파일 해시·기준 SHA·공식 출처·최신성·8단계 결과를 검사합니다.
해시는 파일 변조 검사용이며 실제 수집 또는 카드 사진 육안 검증을 증명하는 서명이 아닙니다.
새 자료 PR은 클라우드 재수집으로 덮어쓰지 않습니다. 일반 코드 PR의 기존 실수집 검증은 유지합니다.
모든 필수 CI 결과를 확인한 뒤 main으로 병합합니다. 자동 main push/강제 push는 없습니다.

PSA/BGS가 태블릿에서도 차단되면 업로드를 중단하고 실행 폴더에 로그/자료를 보존합니다.
공식 사이트 접근 제한을 해제하거나 우회하는 기능은 아닙니다.
수집 중 main이 바뀌거나 CI에 도착할 때 자료가 만료되면 최신 main에서 다시 수집합니다.
오래된 영수증의 시각을 수정해 통과시키지 않습니다.

PR 병합 전 업로드 없이 로컬 수집만 확인하려면 `python tablet_collection_publish.py`를 실행합니다.
GitHub 인증은 태블릿에서 직접 진행하며 토큰을 채팅이나 저장소에 넣지 않습니다.

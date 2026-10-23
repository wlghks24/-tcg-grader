# 태블릿 화면 확인과 적용 마무리

코드 수정은 PR #802에 저장되어 있다. CI·DOM 검사와 실제 기기의 렌더·터치·렉 측정은 별개다.
`execution/tablet_local_ui_review.py`는 운영 설치가 아닌 임시 소스 검토 도구다.

## 태블릿 Termux에서 후보 화면 확인

기존 TCG 저장소 디렉터리에서 실행한다. 기존 작업파일·사진·학습자료는 덮어쓰지 않는다.

```bash
git fetch origin fix/tablet-local-ui-learning-v652-20261023
review_dir="$(mktemp -d ../tcg-ui-review.XXXXXX)"
git worktree add --detach "$review_dir" FETCH_HEAD
python "$review_dir/execution/tablet_local_ui_review.py" --open-browser
```

Termux 브라우저 열기가 지원되지 않으면 출력된 `http://127.0.0.1:포트/__review`를 같은 기기 브라우저에서 연다.
포트는 기본적으로 빈 임시 포트다. **화면 점검 실행**을 누르면 360px·1024px에서 실제 브라우저가
카테고리·기능 이동·출시/행사/구매처 내부패널·국가 선택·터치 높이·가로 넘침을 점검한다.
기존 서비스워커·브라우저 캐시·localStorage를 지우지 않는다.

결과는 새 worktree의 `.tmp/local-ui-review/*.json`과 브라우저의 **결과 JSON 저장**에 남는다.
브라우저가 보고한 관찰값이며 독립 검증·실기기 인증·배포 승인을 자동으로 부여하지 않는다.
실패 항목이 있으면 해당 결과와 화면을 검토해 수정한다. 보고서가 없거나 점검이 중단되면 통과가 아니다.

모든 운영 API·외부 연결·서비스워커 등록은 이 검토 서버에서 차단된다.
따라서 서버 연결 경고는 예상되는 미리보기 제한이다. 이 도구는 실제 카드사진/카드정보,
촬영, 수집, 학습, PWA 갱신 또는 실기기 성능을 검증하지 않는다. 이 항목은 운영 적용 후 별도로 확인한다.
화면을 눈으로 확인하고, 결과 JSON과 문제가 있는 화면을 전달하면 실제 렌더 관찰과 코드 검사를 대조할 수 있다.
종료는 Termux에서 Ctrl+C다. 이 검토로 운영 main이나 기존 태블릿 설치가 변경되지는 않는다.

## 운영 적용

현재 PR의 정확한 HEAD·검토 결과·CI와 렌더 결과를 확인해 main에 병합한 뒤,
기존 데이터 보존 업데이트 경로를 사용한다. 미리보기 브랜치를 운영 main 대신 설치하지 않는다.

```bash
python execution/tablet_preserved_update.py --apply --start --enable-images
bash RUN_RUNTIME_BENCHMARK.sh --requests 24 --concurrency 2
./main learn-status
```

실제 기기에서 국가 전환, 가운데 촬영 버튼, 이미지 관리 이동, 저장 이미지의 카드 상세,
누락정보 상태, 학습 저장량/가능량과 자동 수집 상태를 확인한다.
학습 기준량·클래스·시간분할·holdout을 충족해야 모델이 활성화되며, 기준 미충족은 자료를 누적하면서 대기한다.
외부 403/429·자료 결손은 우회하거나 정상으로 숨기지 않는다.

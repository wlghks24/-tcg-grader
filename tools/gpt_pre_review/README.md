# GPT First-Review / Historical Failure Gate (TCG Grader)

한국어: 이 폴더는 **코드 리뷰 이전의 오프라인 증거 검사기**입니다. 연결된 GPT가 PR 원문과 실제 diff 및 최신 실행 로그를 독립적으로 읽고 교차검증하도록 돕습니다. Python 표준 라이브러리만 사용하며 유료 API·새 서버·예약 스케줄은 추가하지 않습니다.

## 검증 방법
1. PR의 **실제 head SHA / base SHA**, 변경 파일 전수와 diff를 읽고 설명이 일치하는지 확인합니다.
2. `history_cases.json` 13건과 변경 범위를 교차 비교합니다. PR #640 유형처럼 OCR 변경이라면 `tablet_alignment` 증거가 반드시 필요합니다.
3. 결함 수정 전/후 반례를 테스트합니다. 대상 테스트와 기존 보호 기능 테스트는 별도로 수행합니다.
4. CodeQL, Repository Integrity, Tablet GPT Main Alignment, Exhaustive SELFREFINE 등을 **정확한 PR HEAD**로 조회합니다. 어느 하나라도 실패하면 BLOCKED입니다.
5. 관련 이슈·리뷰 댓글의 해결 여부, 리뷰 작성자의 권한, 필수 상태검사 및 base 업데이트 여부를 확인합니다.
6. GPT에서 재현/교차검증을 완료한 뒤에만 `GPT_PREAPPROVAL_CANDIDATE`라 표시합니다. 이것은 GitHub의 공식 `APPROVED` 리뷰, 병합 또는 실태블릿 배포 승인이 아닙니다.

### 검사기 실행
```bash
cd tools/gpt_pre_review
python -m unittest -v test_pre_review.py
python pre_review.py --snapshot your_pr_snapshot.json --out pre_review_report.json
```
입력 JSON 예시는 아래 참고. `status=pass`는 `proof`와 동일한 40자리 커밋 SHA가 필요한데, 문자열을 입력했다는 사실만으로 검증 완료를 의미하지 않습니다. 증거 점수 100/100 역시 **작성된 증거 범위 점수**이며 제품 성능 점수가 아닙니다.

```json
{
  "pr":{"number":640,"head_sha":"7609b36750202af8b6c06bb230200af3bfc6306f","base_sha":"ce3e411f36e551dc665b5acaac31a81e4c9cd257","mergeable":true,"scope_verification":"diff_and_paths_checked","changed_paths":["card_identity_recognition.py"]},
  "reviewed_head_sha":"7609b36750202af8b6c06bb230200af3bfc6306f",
  "gates":{"tablet_alignment":{"status":"fail","head_sha":"7609b36750202af8b6c06bb230200af3bfc6306f","proof":"Main Alignment failed"}},
  "unresolved_high_findings":[],
  "unresolved_review_threads":0,
  "ci":{"head_sha":"7609b36750202af8b6c06bb230200af3bfc6306f","runs":[{"name":"Tablet GPT TCG Grader Main Alignment","head_sha":"7609b36750202af8b6c06bb230200af3bfc6306f","status":"completed","conclusion":"failure"}]}
}
```
이 샘플은 PR #640 당시 검증 차단을 재현하기 위한 것이며, 최신 상태를 대변하지 않습니다. 실제 진행에서는 GitHub를 **매번 재조회**해야 합니다.

## 실패를 규칙으로 학습한 사례
- #458: CodeQL 지적과 스택 변경 범위 → 미사용 코드 연결·테스트·설명 범위 교정.
- #478: 확장 UI는 있는데 BOX·가격 수집 부족 → 실제 데이터 흐름을 끝까지 검증.
- #578: 이미지 URL 검증과 가격 출처 혼용 → 신뢰 경계를 분리하고 옵션 실패를 격리.
- #640 / #570: 일부 단위검사 통과하지만 역사적 동기화 실패 → 테스트 삭제 금지·정식 successor 세대 검증.
- #573 / #597 / #616 / #619: 오래된 브랜치·manifest·기존 보호경로 충돌 → 최신 main 기반으로 정확한 변경만 이식.
- #649: 공식 BOX 근거 부족·UTC/KST 문제 → 미확인 가격 임의 보간 금지, 날짜 경계 재현.

종료·미병합은 공식 리뷰어의 '반려'와 다르며, 병합은 명시적 승인 리뷰와 다릅니다. `history_cases.json`의 사유는 확인 가능한 PR 기록을 바탕으로 했으나 모든 과거 채팅을 빠짐없이 읽었다는 뜻은 아닙니다.

## 무료 원칙
저장소 공개(Public) 여부를 매번 확인해야 하며, 표준 GitHub-hosted runner의 공개 저장소 Actions는 무료입니다. 단 **대형 러너·스토리지·Codespaces·Copilot·외부 API** 등은 별도 과금될 수 있습니다. 이 모듈은 Actions workflow를 만들거나 수정하지 않습니다. 기존 워크플로는 PR 생성 시 자동 실행할 수 있으며, Gross 사용량과 Billed 금액은 다릅니다.

## 출처 / 자료 신뢰도
- Google Engineering Practices: https://google.github.io/eng-practices/review/reviewer/looking-for.html
- Google small changes: https://google.github.io/eng-practices/review/developer/small-cls.html
- GitHub protected branches: https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches
- GitHub latest-head check: https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/troubleshooting-required-status-checks
- GitHub Actions billing: https://docs.github.com/en/billing/concepts/product-billing/github-actions
- GitHub official YouTube PR explanation: https://www.youtube.com/watch?v=nCKdihvneS0
- Instagram: 공개 게시물 개별 원문에 검증 가능한 기술·라이선스 근거를 확보하지 못한 자료는 **승인 근거로 사용하지 않음**.

## 새 변경과 연동
다른 프로젝트가 아닌 **TCG 태블릿 카드 프로젝트에서만 GitHub 직접 조회·PR 작성 예외 허용**. 본 폴더 추가로 기존 runtime, main 자동갱신 경로, 태블릿 sync watched path, CodeQL 설정, 기존 필수 검사, 보안 규칙을 약화하지 않습니다. 실제 변경은 별도 브랜치·PR에서 검증하고 안전할 때만 main에 병합합니다.

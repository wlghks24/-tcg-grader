# 미구현·오류·누락 보완 작업 추적

기준: PR #921 `b6d3496d606ad4497cda32dad51dbc1d8e709f09`.

## 추가 동작

- 기존 문법/인코딩 오류, 위험 패턴, 과거 미해결 결함, 검사 제외 파일 분류에 더해 pass/생략형 함수와 명시적인 NotImplementedError를 정적으로 탐지한다.
- 추상 메서드·프로토콜·의도된 빈 함수일 수 있으므로 REVIEW_REQUIRED로만 기록한다. 기능 누락이나 실제 결함이 입증됐다는 뜻은 아니다.
- priority_items에서 모든 필드가 같은 증거만 합친다. 다른 파일·줄·결함 ID는 보존한다.
- implementation_backlog.json에 task_id, source_head_sha, line, summary, repair_strategy, next_steps를 추가한다. 원본 확인 → 실패 동작 테스트 → 격리 구현 → 회귀/보안/successor/현재 HEAD CI 순서로 보완할 수 있다.
- 기존 인증 플래그 strict-True 격리 패치 후보 생성과 독립 검증을 유지한다. 임의의 새 기능이나 학습/저장 로직을 추측으로 자동 구현하지 않는다.
- 모든 과제는 implementation_verified=false, automatic_apply_allowed=false 상태다. 코드가 있다는 사실을 수정 완료 증거로 사용하지 않는다.

## 사용 및 제한

새 코드로 새 보고서 출력 폴더를 선택해 기존 전체 검수 버튼이나 CLI를 사용한다. 기존 보고서는 재현성 보호 때문에 덮어쓰지 않는다. 이전 형식과 비교가 불일치하면 새 출력 폴더가 필요하다.

이 변경은 수정할 위치와 절차를 코드로 연결한 기능이며 모든 미구현 기능을 구현한 패치가 아니다. 실제 동작·Windows 실기기 검증·보호된 runtime successor·전체 현재 HEAD CI는 별도다. 기존 학습 보안 PR #922와 중복 수정하지 않는다.

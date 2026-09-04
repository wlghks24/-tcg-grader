# Instagram TCG Content Domain

이 디렉터리는 인스타그램 TCG 캐러셀 제작 전용 도메인입니다.

목적:
- Pokémon / ONE PIECE / NARUTO 정보 수집·검증
- 10:00 KST / 조건부 22:00 KST 기준 데이터 확인
- 완료거래 / 시장참고 / 출시 / 프로모 / 이벤트 / 영화 정보 분리
- KR / EN 캐러셀 렌더링
- 출처 코드 / 해시태그 / 게시용 패킷 생성
- Instagram 전용 SELFREFINE 상태 관리

공유:
- shared_self_learning/의 순수 알고리즘과 계약만 사용
- crosscheck_exchange/를 통한 passive factual JSON 교차검증만 허용

분리:
- Main 코드 import 금지
- Main collector/OCR/grading/runtime 호출 금지
- Main error ledger/retry/provider/learning state 공유 금지
- Instagram error ledger는 INSTAGRAM SELFREFINE 전용 파일로 독립
- Instagram 오류를 Main SELFREFINE 오류로 합산하지 않음

정보가 같더라도 각 도메인의 source lineage와 verification은 독립적으로 유지합니다.

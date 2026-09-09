# Instagram TCG Content Domain

이 디렉터리는 인스타그램 TCG 캐러셀 제작 전용 도메인입니다.

목적:
- Pokémon / ONE PIECE / NARUTO 정보 수집·검증
- 10:30 KST 정규 제작 / 조건부 22:30 KST 수정 기준 데이터 확인
- 완료거래 / 시장참고 / 출시 / 프로모 / 이벤트 / 영화 정보 분리
- KR / EN 캐러셀 렌더링
- 출처 코드 / 해시태그 / 게시용 패킷 생성
- Instagram 전용 SELFREFINE 상태 관리

운영 기준:
- 정규 스케줄은 10:30 KST이며 이때만 당일 baseline을 생성한다.
- 22:30 KST는 10:30 baseline 대비 VERIFIED material diff가 있을 때만 수정판을 생성한다.
- 일반 감시 실행은 baseline을 생성하거나 과거 시각으로 timestamp를 재라벨링하지 않는다.

공유:
- shared_self_learning/의 순수 알고리즘과 계약만 사용
- 사실 검증은 IG_CARDINFO 자체 source route와 factual snapshot만 사용
- Main/카드시세분석 factual snapshot, crosscheck_exchange, peer-learning 결과는 검증 근거로 사용하지 않음
- production finalization 전 source_verification_engine의 tamper-evident verification receipt를 production_state가 검증해야 함

분리:
- Main 코드 import 금지
- Main collector/OCR/grading/runtime 호출 금지
- Main error ledger/retry/provider/learning state 공유 금지
- Instagram error ledger는 INSTAGRAM SELFREFINE 전용 파일로 독립
- Instagram 오류를 Main SELFREFINE 오류로 합산하지 않음

정보가 같더라도 각 도메인의 source lineage와 verification은 독립적으로 유지합니다.

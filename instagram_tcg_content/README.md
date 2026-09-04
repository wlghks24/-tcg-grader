# Instagram TCG Content Domain

이 디렉터리는 인스타그램 TCG 캐러셀 제작 전용입니다.

목적:
- Pokémon / ONE PIECE / NARUTO 정보 수집
- 10:00 KST / 22:00 KST 기준 데이터 검증
- 완료거래 / 시장참고 / 출시 / 프로모 / 이벤트 / 영화 정보 분리
- KR / EN 6장 캐러셀 렌더링
- 출처 코드 / 해시태그 / 게시용 패킷 생성
- 이 도메인 전용 SELFREFINE

금지:
- Main TCG Grader SELFREFINE ledger, retry history, learning state 공유
- Main grading/OCR/runtime collector를 이 도메인의 collector로 등록
- 이 도메인의 오류를 Main SELFREFINE 오류로 합산
- Main 코드에서 instagram_tcg_content 모듈 import
- instagram_tcg_content에서 Main runtime 모듈 import

도메인 간 데이터 교환이 필요하면 실행상태나 학습값을 공유하지 않고 명시적인 JSON 데이터 계약만 사용합니다.

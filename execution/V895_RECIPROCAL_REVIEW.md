# V895 카드정보 → 특정 공식 이미지 수집 보완

기존 사진→카드정보 보완은 TCGdex의 기존 사진을 실제 private index에서 채우지만, 반대 방향은 제공처 순환 우선순위만 바꿨다. 이제 fresh/HEALTHY한 source_catalog의 CATALOG_NEEDS_IMAGE 중 명시적 TCGdex 카드 상세 API URL이 있고 게임·국가·언어·세트·카드코드가 검증되는 항목은 특정 이미지를 직접 요청할 수 있다.

기존 동일 Budget, can_save, fetch_json/fetch_binary, library.save_image 및 completed를 재사용한다. 실행당 최대1개 목표, 실패6시간대기, 7일 출처 신선도, 기존 요청/용량/시간/403·429 제한이 적용된다. 원래 사진 수집과 목표 수집의 saved/bytes/scanned를 합산한다. 사진과 함께 상세 응답의 카드번호·세트·언어·희귀도 등을 저장한다.

이미지 URL의 locale/set/localId까지 응답 ID와 대조하고, Pocket/다른 국가/다른 카드/세트/임의호스트를 거부한다. 원래 completed로 삭제된 사진을 재요청하지 않으며 기존 사진을 중복 다운로드하지 않는다. 이미지 아트만으로 printing·등급을 추정하거나 source의 printing을 복사하지 않는다. 판본 미확인 상태는 기존 연결 게이트에 남는다.

로컬19개 PASS(기존 메타데이터10+신규상호보완9): 실제 private 이미지·카드정보 저장/재조회, 중복·삭제, ID/세트/이미지경로 충돌, 미지원/오래된 출처, 실패재시도, 기존사진, 실제요청쿼터 차단, 실행당1개제한 및 현재 V888의 반대방향 이미지→메타데이터 실제보완/원본불변도 검사했다. 외부 API/실제 사용자 사진 수집은 하지 않았고 응답/파일은 fixture다. 모든 제공처의 보편 자동 해결이 아니며 현재는 공식 식별자를 확보한 TCGdex 인쇄카드만 해당한다. 태블릿 적용/학습/실기 판독성 미검증.

공식 API 자료: https://tcgdex.dev/rest/card 및 https://tcgdex.net/ . 새 HEAD 전체 회귀는 기존 GitHub workflow에 등록했다.

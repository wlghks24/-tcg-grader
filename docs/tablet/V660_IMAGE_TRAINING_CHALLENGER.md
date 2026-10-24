# 이미지 학습 후보 엔진: 구현 범위와 미완료 항목

이 변경은 실제 이미지에서 신경망 가중치를 학습하고 평가하는 로컬 후보 엔진이다.
전체 등급 인식 제품의 자동 재학습 완료나 태블릿 설치 완료가 아니다.

`python -m execution.tablet_image_training --root PHOTO_ROOT --manifest LOCAL_REVIEWED_MANIFEST --output LOCAL_MODEL_DIRECTORY --train`

입력은 schema=1, rows 배열이다. 각 행에는 review_method=local_human_raw_photo_pair,
mode=raw, game, language(KR/JP/US/CN-S/CN-T), company, certification_id,
card_identity(정확한 세트/판본/번호), image(root 아래 상대 경로), image_sha256이 필요하다.
이 로컬 검토 입력을 웹 수집기가 작성하도록 연결하지 않는다.
기존 공식 인증 registry에 일치하는 등급이 있어야 하며, 원본 사진과 인증의 연결은
실제 사진을 확인한 검토자가 제공해야 한다. 웹 사진이나 OCR 추정값을 정답으로 만들지 않는다.

한 번에 새 사진 최대 16개/128MB를 처리하고 검증된 특징값을 원자적으로 누적한다.
사진당 최대 8MB/2천만 픽셀, 전체 4천 행, 최대 8개 게임/언어/등급사 그룹이다.
인증 번호·픽셀 특징 중복은 제외한다. 공식 인증이 삭제/변경되면 저장 특징도 학습에서 제외한다.
사진이 지워져도 승인 당시 해시와 연결된 과거 특징 기록을 재사용할 수 있다.

학습 최소 기준은 그룹당 독립 사진 1천 개, 각 분할 100개, 각 클래스 100개다.
인식은 인증 개체 단위, 등급은 카드 판본 식별 단위로 분리한다.
학습·검증·holdout의 역할을 분리하고 game/language/grader별로 섞지 않는다.
학습은 8개 은닉 노드, 최대 12epoch/30초이며 같은 데이터의 학습은 반복하지 않는다.
신규 패키지·유료 API·클라우드·추가 예약은 없다. 기존 Pillow와 표준 Python을 쓴다.

현재 특징은 8×8 RGB 축소 특징이다. 파이프라인 작동을 확인하는 작은 기준 모델이며
미세 흠집·백화·모서리를 판독하는 고해상도 등급 모델이 아니다.
실물 정확도, 등급 오판율, 확률 보정, 기존 모델 대비 개선을 입증하지 않았다.
후보는 별도 *.challenger.json으로만 저장하며 현행 OCR/등급 보정과 모델은 교체하지 않는다.

남은 작업: 고해상도/결함 특징과 신뢰 가능한 원본 정답 데이터, 챔피언 비교·보정·회귀·롤백,
기존 단일 6시간 감시 루프 연결, 카드 상세 추론 연결, 태블릿 CPU/메모리·재부팅 검증.
진단 명령과 후보 학습 명령을 자동학습 활성화 또는 등급 정확도 향상으로 보고하지 않는다.

공식 참고: https://pillow.readthedocs.io/en/stable/reference/Image.html
픽셀 처리의 get_flattened_data와 이미지 디코딩 한도를 검토했다.

후속 V661: 기존 6시간 루프 연결, 원본 해상도 영역 특징, 보조 모델 비교·선정·마지막 정상본 복구 구현은 [V661_IMAGE_AUTOMATION.md](V661_IMAGE_AUTOMATION.md)를 참조한다. 이 문서의 8×8 단독 특징과 미연결 설명은 V660 당시 상태다.

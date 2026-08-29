# TCG Grader v109 실행 안내

이 문서가 현재 실행 기준입니다. `사용방법_v79.md`~`사용방법_v99.md`는 개발 이력 보관용이며 현재 실행파일 안내가 아닙니다.

## Windows PC

1. ZIP을 새 폴더에 완전히 압축 해제합니다.
2. Python 3를 설치하고 `Add Python to PATH`를 선택합니다.
3. `START_TCG_UPDATER.bat`을 실행합니다. 사진검증용 Pillow가 없으면 `requirements.txt`에서 자동 설치합니다.
4. 자동으로 열린 `http://127.0.0.1:8765/index.html`을 사용합니다.
5. 로그인할 때 서버 자동실행이 필요하면 `PC_SERVER_AUTO_START_INSTALL.bat`을 한 번 실행합니다.
6. 자동실행 해제는 `PC_SERVER_AUTO_START_REMOVE.bat`을 실행합니다.

자료 7단계 업데이트와 5회 검사는 `TCG_AUTO_UPDATE.bat`, 검사만 실행할 때는 `RUN_FULL_VERIFICATION.bat`을 사용합니다.

Node.js는 앱 실행에 필요하지 않습니다. 라벨 OCR까지 사용하려면 Tesseract OCR을 설치하고 `tesseract` 명령이 PATH에 보여야 합니다. 미설치 시에도 수집·이미지 유효성 검사는 작동하고 OCR 항목만 보류됩니다. Node.js가 설치되어 있으면 JavaScript·카메라·서비스워커 런타임 검사까지 실행하고, 없으면 해당 개발용 검사만 명확히 건너뜁니다. 배포 전 엄격검사는 `TCG_REQUIRE_NODE=1` 환경에서 수행합니다.

## Android 태블릿·Termux

1. ZIP을 태블릿 저장소에 압축 해제합니다.
2. Termux에서 Python을 설치합니다.
3. 프로젝트 폴더에서 `bash START_TCG_UPDATER_ANDROID.sh`를 실행합니다. 최초 실행 시 Pillow와 Tesseract가 없으면 설치를 시도합니다.
4. 재부팅 자동실행 설정은 `bash ANDROID_AUTO_START_INSTALL.sh`, 해제는 `bash ANDROID_AUTO_START_REMOVE.sh`를 실행합니다.
5. 같은 Wi-Fi의 iPhone에서는 Termux 화면에 표시된 태블릿 주소로 접속합니다.

## macOS·Linux

프로젝트 폴더에서 `python3 -m pip install -r requirements.txt` 후 `python3 tcg_updater.py`를 실행합니다. 라벨 OCR에는 시스템 Tesseract도 필요합니다.

## 현재 검사 명령

- 1회 현재 릴리스 검사: `python3 verify_v109_final.py`
- 5회 반복검사: `python3 run_repeated_verification.py --passes 5`
- 기존 호환 명령: `python3 verify_all.py`도 현재 v109 검사기를 실행합니다.
- v79~v99 과거 단언 모음: `verify_all_legacy_v99.py`이며 현재 정상 여부 판정에는 사용하지 않습니다.

## 기능 범위

- Pokémon·ONE PIECE·NARUTO, 한국·일본·미국
- 등급사진 수집은 포켓몬·원피스·나루토를 출처별 라운드로빈으로 균등 탐색하며, 어느 한 게임의 검색 결과가 수집 한도를 독점하지 않습니다.
- PSA·BGS·CGC·TAG·BRG 사진 기반 1~10 사전측정
- 자동 앞·뒷면 촬영, 흔들림 보류, 센터링·코너·엣지·백화·표면 분석
- 앞면 카드명·카드번호 OCR, 사용자 확인형 이미지학습, 인식 후 시세검색 자동 연결
- BOX/HIT·출시·재발매·시세·원화환산·행사·콜라보·영화·구매처
- Instagram·X·Google 후보 수집과 공식/보조 출처 분리
- eBay·Amazon·KREAM·당근 등 공개 검색 후보, 이미지 유효성 검사·라벨 OCR·PSA/BGS/CGC/TAG/BRG 인증번호 공식 교차검증
- 공식 인증번호·업체·등급이 모두 일치한 자료만 슬랩 참고학습에 등록하며, 원본 카드 결함 보정학습과는 분리
- 6시간 반영, 30분 전 사전수집, 시간초과 대상만 별도 재수집

등급사진 강화 수집은 로컬 화면의 `강화 수집 실행` 버튼으로 별도 실행할 수 있습니다. eBay Browse API는 `EBAY_OAUTH_TOKEN` 또는 `EBAY_CLIENT_ID`·`EBAY_CLIENT_SECRET`, Google 이미지/웹 검색은 기존 Custom Search 고객의 `GOOGLE_CSE_API_KEY`·`GOOGLE_CSE_ID`를 설정하면 우선 사용하고, 미설정 시 공개 검색 인덱스로 폴백합니다. 로그인·CAPTCHA·robots 제한은 우회하지 않습니다.

사진 측정값은 공식 감정등급이 아닌 보수적인 사전검사 참고값입니다. Hough 선분은 확정 스크래치가 아니라 장선형 결함 후보로만 사용합니다. GitHub 토큰과 API 키는 웹앱 코드에 넣지 않습니다.

## 자료 이전·백업

- 이전 버전 학습자료 가져오기: `MIGRATE_OLD_TCG_DATA.bat`
- 현재 학습자료 백업: `BACKUP_TCG_LEARNING_DATA.bat`

iPhone 단독 서버리스 지속수집 기능은 사용자 요청에 따라 포함하지 않습니다.

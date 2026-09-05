# 레노버 안드로이드 태블릿 서버 실행

이 설명은 레노버를 포함한 일반 안드로이드 태블릿에 적용됩니다. iPad는 iOS 제한 때문에 Python 서버를 직접 계속 실행하는 방식이 지원되지 않으며, PC 또는 안드로이드 서버 주소로 접속해 사용합니다.

## 처음 한 번만 설치

1. 태블릿에 **F-Droid**를 설치하고 F-Droid에서 **Termux**를 설치합니다.
   Google Play의 오래된 Termux는 사용하지 마세요.
2. Termux를 열고 아래 명령을 한 줄씩 실행합니다.

```sh
termux-setup-storage
pkg update -y
pkg install python git -y
```

3. 저장공간 권한 질문이 나오면 **허용**을 누릅니다.
   권한 창이 안 나오면 설정 → 앱 → Termux → 권한 → 파일 및 미디어를 허용합니다.
4. 아래 명령으로 실제 GitHub 저장소 전체 주소를 복사하여 설치합니다.

```sh
git clone https://github.com/wlghks24/-tcg-grader.git
cd ./-tcg-grader
```

`https://github.com/wlghks24`만 입력하면 저장소 이름이 없어 `repository not found`가 나타납니다. URL을 단독으로 입력하지 말고 반드시 앞에 `git clone`을 붙이세요. 이미 설치한 경우에는 `cd ./-tcg-grader` 다음 `bash ANDROID_UPDATE_AND_START.sh`를 실행하세요. 코드/설정에 사용자가 만든 로컬 수정이 있으면 자동으로 덮어쓰지 않고 업데이트를 건너뛰며, 알려진 런타임 JSON은 백업 후 안전하게 처리합니다. 업데이터 자체가 오래되어 갱신이 막힌 경우에만 `bash ANDROID_RECOVER_UPDATE.sh`를 사용합니다.

ZIP으로 설치하는 경우에만 압축을 풀어 `Download/TCG_GRADER` 폴더에 둡니다.

## 서버 시작

GitHub로 설치했다면 Termux에서 아래 두 줄을 실행합니다. 이 경로가 **기본 실행 방법**입니다. 공식 GitHub `main`을 안전하게 확인하고, 기기 로컬 학습자료·사진을 보존한 뒤 최신 코드로 fast-forward 가능한 경우에만 갱신하고 서버를 시작합니다.

```sh
cd ./-tcg-grader
bash ANDROID_UPDATE_AND_START.sh
```

이미 `-tcg-grader` 폴더 안이라면 첫 줄 없이 `bash ANDROID_UPDATE_AND_START.sh`만 실행합니다. 단순히 서버만 시작해야 하는 진단 상황이 아니라면 `START_TCG_UPDATER_ANDROID.sh`를 직접 실행하지 않는 것을 권장합니다. ZIP으로 설치한 경우에는 대신 아래 명령을 사용합니다.

```sh
cd ~/storage/downloads/TCG_GRADER
bash START_TCG_UPDATER_ANDROID.sh
```

화면에 표시되는 `이 기기 접속 주소`를 태블릿 Chrome에서 엽니다. 같은 Wi-Fi의 휴대폰이나 PC에서는 `다른 기기 접속 주소`를 엽니다. 서버 사용 중에는 Termux를 완전히 종료하지 마세요.

정상 확인 주소는 `http://127.0.0.1:8765/api/v135-health`입니다. 응답의 `ok` 값이 `true`이면 현재 Android 안전서버가 정상입니다. 같은 Wi-Fi의 다른 기기에서는 화면에 표시된 `http://192.168.x.x:8765/index.html` 주소를 사용합니다.

서버가 먼저 열리고 자료 수집은 백그라운드에서 시작 직후와 6시간마다 실행됩니다. 출시일, 판매·재발매, 현재 시세, 공식 행사, 구매처 HTTPS 링크, 환율의 6개 항목을 확인합니다. 이미 열린 화면은 1분마다 최신 자료를 자동 반영합니다. 일부 공식 사이트가 일시적으로 접속을 제한하면 기존 정상 자료를 유지하고 다음 주기에 다시 확인합니다.

- 자동수집 상태: `http://127.0.0.1:8765/api/auto-status`
- 최근 수집 보고: `http://127.0.0.1:8765/api/update-report`

## 선택 기능: Graphify 코드 지도

이 태블릿은 Mac/Windows가 아니라 **Android + Termux**이므로 Graphify도 Termux 방식으로 설치합니다. 프로젝트 폴더에서 아래 한 줄을 실행하면 Python 3.10+ 확인, `uv` 또는 `pipx` 설치 경로 선택, `graphify --version` 검증, OpenAI/Codex 프로젝트 연동, 최초 코드 지도 생성, Git 자동 갱신 훅 설치까지 순서대로 진행합니다.

```sh
bash SETUP_GRAPHIFY_TERMUX.sh
```

설치 후 코드 지도 갱신:

```sh
bash GRAPHIFY_UPDATE.sh
```

또는 Graphify CLI 직접 사용:

```sh
graphify update .
```

Codex 프로젝트에서는 Graphify 스킬 호출 문법이 `/graphify`가 아니라 `$graphify`입니다. 자세한 초보자용 설명과 PATH 오류 해결은 `GRAPHIFY_CHATGPT_GUIDE.md`를 확인하세요.

## 태블릿을 켤 때 자동 실행

1. F-Droid에서 **Termux:Boot**를 설치합니다.
2. 설치한 Termux:Boot 앱을 한 번 열었다가 닫습니다.
3. Termux에서 프로그램 폴더로 이동합니다.
4. `bash ANDROID_AUTO_START_INSTALL.sh`를 한 번 실행합니다.
5. 태블릿 설정에서 Termux와 Termux:Boot의 배터리를 **제한 없음**으로 설정합니다.
6. 다음 태블릿 재시작부터 TCG 서버가 자동 실행되고 시작 직후와 6시간마다 자료를 갱신합니다. 서버가 비정상 종료되거나 건강검사에 실패하면 30초부터 재시도하며, 반복 실패 시 최대 5분까지 지수형으로 대기해 과도한 재시작을 막습니다.

자동실행 기록은 `TCG_ANDROID_STARTUP.log`에서 확인합니다. 자동실행을 해제하려면 `bash ANDROID_AUTO_START_REMOVE.sh`를 실행합니다.

## 안드로이드 절전 설정

- 설정 → 앱 → Termux → 배터리 → **제한 없음**으로 변경합니다.
- Termux:Boot도 동일하게 **제한 없음**으로 변경합니다.
- 장시간 수집할 때는 충전기에 연결합니다.
- 외부 인터넷에 포트를 공개하지 말고 같은 Wi-Fi 안에서만 사용합니다.

## 연결이 안 될 때

1. 태블릿과 접속 기기가 같은 Wi-Fi인지 확인합니다.
2. 주소 끝에 반드시 `:8765/index.html`을 붙입니다.
3. VPN을 끄고 다시 실행합니다.
4. Termux 창에 오류가 없는지 확인하고 `bash START_TCG_UPDATER_ANDROID.sh`를 다시 실행합니다.
5. `127.0.0.1`은 태블릿 자체에서만 사용합니다. 다른 기기는 `192.168.x.x` 주소를 사용합니다.
6. 공유기의 AP 격리·게스트 Wi-Fi가 켜져 있으면 기기끼리 연결되지 않으므로 일반 Wi-Fi를 사용합니다.

## 자동실행 확인

태블릿을 재시작하고 잠금 해제한 뒤 Chrome에서 `http://127.0.0.1:8765/api/v135-health`를 엽니다. 연결되지 않으면 Termux:Boot를 한 번 열고, 두 앱의 배터리 제한과 자동 시작 권한을 다시 확인합니다. 기록은 프로그램 폴더의 `TCG_ANDROID_STARTUP.log`에 저장됩니다.

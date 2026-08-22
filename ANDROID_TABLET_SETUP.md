# 레노버 안드로이드 태블릿 서버 실행

이 설명은 레노버를 포함한 일반 안드로이드 태블릿에 적용됩니다. iPad는 iOS 제한 때문에 Python 서버를 직접 계속 실행하는 방식이 지원되지 않으며, PC 또는 안드로이드 서버 주소로 접속해 사용합니다.

## 처음 한 번만 설치

1. 태블릿에 **F-Droid**를 설치하고 F-Droid에서 **Termux**를 설치합니다.
   Google Play의 오래된 Termux는 사용하지 마세요.
2. Termux를 열고 아래 명령을 한 줄씩 실행합니다.

```sh
termux-setup-storage
pkg update -y
pkg install python -y
```

3. 저장공간 권한 질문이 나오면 **허용**을 누릅니다.
   권한 창이 안 나오면 설정 → 앱 → Termux → 권한 → 파일 및 미디어를 허용합니다.
4. ZIP 압축을 풀어 `Download/TCG_GRADER` 폴더에 둡니다.

## 서버 시작

Termux에서 아래 두 줄을 실행합니다.

```sh
cd ~/storage/downloads/TCG_GRADER
bash START_TCG_UPDATER_ANDROID.sh
```

화면에 표시되는 `이 기기 접속 주소`를 태블릿 Chrome에서 엽니다. 같은 Wi-Fi의 휴대폰이나 PC에서는 `다른 기기 접속 주소`를 엽니다. 서버 사용 중에는 Termux를 완전히 종료하지 마세요.

정상 확인 주소는 `http://127.0.0.1:8765/api/health`입니다. `{"ok": true}`가 보이면 서버가 정상입니다. 같은 Wi-Fi의 다른 기기에서는 화면에 표시된 `http://192.168.x.x:8765/index.html` 주소를 사용합니다.

## 태블릿을 켤 때 자동 실행

1. F-Droid에서 **Termux:Boot**를 설치합니다.
2. 설치한 Termux:Boot 앱을 한 번 열었다가 닫습니다.
3. Termux에서 프로그램 폴더로 이동합니다.
4. `bash ANDROID_AUTO_START_INSTALL.sh`를 한 번 실행합니다.
5. 태블릿 설정에서 Termux와 Termux:Boot의 배터리를 **제한 없음**으로 설정합니다.
6. 다음 태블릿 재시작부터 TCG 서버가 자동 실행되고 시작 직후와 6시간마다 자료를 갱신합니다.

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

태블릿을 재시작하고 잠금 해제한 뒤 약 1분 기다립니다. Chrome에서 `http://127.0.0.1:8765/api/health`를 엽니다. 연결되지 않으면 Termux:Boot를 한 번 열고, 두 앱의 배터리 제한과 자동 시작 권한을 다시 확인합니다. 기록은 프로그램 폴더의 `TCG_ANDROID_STARTUP.log`에 저장됩니다.

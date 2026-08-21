# 레노버 안드로이드 태블릿 서버 실행

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
4. ZIP 압축을 풀어 `Download/TCG_GRADER` 폴더에 둡니다.

## 서버 시작

Termux에서 아래 두 줄을 실행합니다.

```sh
cd ~/storage/downloads/TCG_GRADER
bash START_TCG_UPDATER_ANDROID.sh
```

화면에 표시되는 `이 기기 접속 주소`를 태블릿 Chrome에서 엽니다. 같은 Wi-Fi의 휴대폰이나 PC에서는 `다른 기기 접속 주소`를 엽니다. 서버 사용 중에는 Termux를 완전히 종료하지 마세요.

## 안드로이드 절전 설정

- 설정 → 앱 → Termux → 배터리 → **제한 없음**으로 변경합니다.
- 장시간 수집할 때는 충전기에 연결합니다.
- 외부 인터넷에 포트를 공개하지 말고 같은 Wi-Fi 안에서만 사용합니다.


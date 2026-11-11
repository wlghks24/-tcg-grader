# Lenovo 태블릿 TCG Grader 설치 가이드 V1004

이 프로젝트는 APK가 아니라 **Android Termux 로컬 서버 + Chrome 홈 화면 PWA**로 설치합니다. 기존 사진·정답 라벨·수집자료·모델·수동 코드 수정은 자동 삭제하지 않습니다.

## 새 Lenovo 태블릿에서 설치

[F-Droid Termux](https://f-droid.org/packages/com.termux/)와 같은 출처의 [Termux:Boot](https://f-droid.org/packages/com.termux.boot/)를 설치합니다. Termux:Boot는 아이콘을 한 번 실행해야 재부팅 자동 실행을 허용할 수 있습니다.

태블릿 Termux에서 한 줄씩 실행하세요.

```bash
pkg update -y
pkg install -y python python-pillow git
git clone https://github.com/wlghks24/-tcg-grader.git "$HOME/-tcg-grader"
cd "$HOME/-tcg-grader"
bash INSTALL_LENOVO_TCG_V1004.sh --check
bash INSTALL_LENOVO_TCG_V1004.sh --install
```

**같은 폴더가 있으면 git clone을 반복하거나 삭제하지 마세요.** 기존에 설치된 경우 다음 절차를 사용합니다.

## 기존 설치 업데이트

```bash
cd "$HOME/-tcg-grader"
bash main update-now
bash INSTALL_LENOVO_TCG_V1004.sh --check
bash INSTALL_LENOVO_TCG_V1004.sh --install
```

원래 설치 폴더 이름이 다르면 그 폴더에서 실행하세요. 기존 main 안전 업데이트가 보류되면 설치를 강행하지 않고 오류를 확인합니다. **git reset --hard, git clean, 데이터 삭제, 강제 병합은 금지**합니다.

## Chrome에서 앱 설치

태블릿 Chrome에서 **http://127.0.0.1:8765/index.html** 을 열어 ⋮ 메뉴의 **앱 설치** 또는 **홈 화면에 추가**를 선택하세요. 사용자가 실제 기기에서 눌러야 하는 별도 단계입니다.

## 기기 검증

```bash
bash INSTALL_LENOVO_TCG_V1004.sh --status
bash main update-status
bash main learn-status
bash VERIFY_TABLET_RUNTIME.sh
```

Termux·Termux:Boot 배터리 사용을 제한 없음으로 설정하고 태블릿 재부팅 후 다시 검사합니다. CI 통과는 실기기 실행 증거가 아닙니다. 시세·수집자료 검증 HOLD는 설치기로 우회하지 않습니다.

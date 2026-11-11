# Lenovo 태블릿 카드 AI — 공식 Termux 설치/검증

이 프로젝트의 설치 대상은 **Android Lenovo + Termux + 로컬 Chrome**입니다. APK가 아닙니다.
GitHub CI 성공은 실기기 설치·카드 촬영·등급 평가 성공을 보증하지 않습니다.

## 1회 준비
1. Lenovo 태블릿에서 F-Droid의 Termux를 설치해 실행합니다.
2. Termux에서 아래 명령을 차례대로 입력합니다. 다운로드 링크만 터치해 Android에 APK를 설치하는 방식이 아닙니다.
3. 이 명령은 **공식 main**만 사용하며, 이미 `~/ -tcg-grader`(공백 제외) 폴더가 있으면 삭제하지 않습니다.

```sh
pkg update -y
pkg install -y git python
git clone --branch main --single-branch https://github.com/wlghks24/-tcg-grader.git "$HOME/-tcg-grader"
bash "$HOME/-tcg-grader/TCG_LENOVO_INSTALL.sh" --install
```

이미 `$HOME/-tcg-grader` 저장소가 있는 경우에는 **git clone 단계는 생략**합니다.

```sh
bash "$HOME/-tcg-grader/TCG_LENOVO_INSTALL.sh" --check
bash "$HOME/-tcg-grader/TCG_LENOVO_INSTALL.sh" --install
```

`--install`은 기존 공식 main만 fast-forward하고, 데이터 보호·검증 규칙이 실패하면 업데이트하지 않습니다.
현재 GitHub에 병합되지 않은 PR 코드는 태블릿에 자동으로 설치되지 않습니다.

## 설치 검증
서버 실행 중 별도 Termux 세션에서 아래 명령을 실행합니다.

```sh
bash "$HOME/-tcg-grader/TCG_LENOVO_INSTALL.sh" --verify
```

성공하면 Chrome에서 <http://127.0.0.1:8765/index.html>을 엽니다.
`--verify` 실패 시 포트 8765가 열려 있는지, Termux에 에러가 없는지 검사합니다.
정확한 기기 설치 확인은 **태블릿에서 출력된 Git SHA, health 응답, UI 화면**으로 따로 합니다.

## 자동 시작 (선택)
F-Droid에서 Termux:Boot를 설치하여 한 번 실행한 후:

```sh
bash "$HOME/-tcg-grader/TCG_LENOVO_INSTALL.sh" --boot
```

Android 설정에서 Termux와 Termux:Boot 배터리 사용을 제한 없음으로 설정합니다.
기존 사진·학습 데이터·로컬 수정 파일을 일괄 삭제하거나 강제로 reset하지 않습니다.
설치 파일은 다른 프로젝트(차량/주식)에 적용하지 않습니다.

## 실패 시
`[HOLD]` 오류는 설치를 멈춘 상태입니다. 해당 오류 로그를 복사하여 분석합니다.
명령이 실패해도 `rm -rf`, `git reset --hard` 같은 삭제·강제 초기화를 실행하지 마세요.
문제가 해결되지 않으면 기존 `ANDROID_UPDATE_AND_START.sh`의 안전 업데이트 규칙을 우선합니다.

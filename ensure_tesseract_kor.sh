#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# Termux's current tesseract package ships English traineddata only.
# Korean is installed directly from the official tesseract-ocr/tessdata_fast
# repository into the same tessdata directory used by the Termux build.

if ! command -v tesseract >/dev/null 2>&1; then
  echo "[OCR] Tesseract가 없어 먼저 설치합니다."
  pkg install tesseract -y
fi

if tesseract --list-langs 2>/dev/null | grep -Fxq 'kor'; then
  echo "[OK] Tesseract 한글 OCR(kor) 이미 설치됨"
  exit 0
fi

PREFIX_DIR="${PREFIX:-/data/data/com.termux/files/usr}"
TESSDATA_DIR="$PREFIX_DIR/share/tessdata"
TARGET="$TESSDATA_DIR/kor.traineddata"
TMP="$TARGET.download"
URL="https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/kor.traineddata"

mkdir -p "$TESSDATA_DIR"
rm -f "$TMP"

echo "[OCR] 공식 Tesseract 한글 학습자료(kor)를 설치합니다..."
python - "$URL" "$TMP" <<'PY'
from pathlib import Path
import sys
import urllib.request

url, target = sys.argv[1], Path(sys.argv[2])
request = urllib.request.Request(url, headers={"User-Agent": "TCG-Grader-Termux/172"})
with urllib.request.urlopen(request, timeout=45) as response:
    data = response.read()
if len(data) < 100_000:
    raise SystemExit(f"download too small: {len(data)} bytes")
target.write_bytes(data)
print(f"[OCR] 다운로드 완료: {len(data):,} bytes")
PY

mv -f "$TMP" "$TARGET"
chmod 644 "$TARGET"

if ! tesseract --list-langs 2>/dev/null | grep -Fxq 'kor'; then
  rm -f "$TARGET"
  echo "[오류] kor.traineddata를 설치했지만 Tesseract가 인식하지 못했습니다."
  exit 1
fi

echo "[OK] Tesseract 한글 OCR(kor) 설치 완료"
tesseract --list-langs 2>/dev/null | grep -E '^(eng|kor)$' || true

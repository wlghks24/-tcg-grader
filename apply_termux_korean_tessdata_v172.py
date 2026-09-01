#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"target not found in {path}: {old[:120]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


start = Path("START_TCG_UPDATER_ANDROID.sh")
anchor = '''if ! command -v tesseract >/dev/null 2>&1; then\n  echo "라벨 OCR용 Tesseract를 설치합니다..."\n  pkg install tesseract -y || echo "[안내] Tesseract 미설치 상태에서는 사진 수집 후 OCR만 보류됩니다."\nfi\n'''
replacement = anchor + '''if command -v tesseract >/dev/null 2>&1; then\n  if ! tesseract --list-langs 2>/dev/null | grep -Fxq 'kor'; then\n    if [ -s "ensure_tesseract_kor.sh" ]; then\n      bash ensure_tesseract_kor.sh || echo "[안내] 한글 OCR 설치를 완료하지 못했습니다. 공식 조회결과 한글 인식만 보류됩니다."\n    else\n      echo "[안내] ensure_tesseract_kor.sh가 없어 한글 OCR 자동설치를 건너뜁니다."\n    fi\n  fi\nfi\n'''
replace_once(start, anchor, replacement)

pending = Path("pending_official_candidate_v161.py")
replace_once(
    pending,
    'ENGINE = "v171-pending-official-candidate-korean-negative-proof-ocr"',
    'ENGINE = "v172-pending-official-candidate-termux-korean-tessdata-bootstrap"',
)
replace_once(
    pending,
    'raise ValueError("한글 공식조회 결과를 읽기 위한 OCR 언어자료가 없습니다. Termux에서 pkg install tesseract-data-kor -y 실행 후 다시 선택하세요.")',
    'raise ValueError("한글 공식조회 결과를 읽기 위한 OCR 언어자료가 없습니다. Termux에서 bash ensure_tesseract_kor.sh 실행 후 다시 선택하세요.")',
)

print("Termux Korean tessdata bootstrap v172 applied")

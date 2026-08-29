#!/bin/sh
cd "$(dirname "$0")"
python3 -c 'from PIL import Image' >/dev/null 2>&1 || python3 -m pip install -r requirements.txt
command -v tesseract >/dev/null 2>&1 || echo "[NOTICE] Install Tesseract OCR to enable graded-label text recognition."
python3 tcg_updater.py

#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"target not found in {path}: {old[:100]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


path = Path("pending_official_candidate_v161.py")

replace_once(
    path,
    "import math\nfrom pathlib import Path\nimport re\nfrom typing import Any\n",
    "import math\nfrom pathlib import Path\nimport re\nimport shutil\nimport subprocess\nimport tempfile\nfrom typing import Any\n",
)

replace_once(
    path,
    'ENGINE = "v163-pending-official-candidate-manual-verification"',
    'ENGINE = "v171-pending-official-candidate-korean-negative-proof-ocr"',
)

replace_once(
    path,
    '''_NEGATIVE_PATTERNS = (\n    re.compile(r"검색된\\s*기록이\\s*없습니다", re.I),\n    re.compile(r"검색(?:된)?\\s*결과가\\s*없습니다", re.I),\n    re.compile(r"조회(?:된)?\\s*기록이\\s*없습니다", re.I),\n''',
    '''_NEGATIVE_PATTERNS = (\n    re.compile(r"검색\\s*(?:된)?\\s*(?:기록|결과)\\s*(?:이|가)?\\s*없(?:습니다|음)", re.I),\n    re.compile(r"조회\\s*(?:된)?\\s*(?:기록|결과)\\s*(?:이|가)?\\s*없(?:습니다|음)", re.I),\n    re.compile(r"(?:일치하는|해당)\\s*(?:기록|결과|인증번호)\\s*(?:이|가)?\\s*없(?:습니다|음)", re.I),\n''',
)

anchor = '''def _save_candidate_payload(payload: dict[str, Any], rows: list[dict[str, Any]], *, promoted_delta: int = 0,\n'''
helper = r'''def _tesseract_languages() -> set[str]:
    binary = shutil.which("tesseract")
    if not binary:
        return set()
    try:
        run = subprocess.run(
            [binary, "--list-langs"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=8, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    raw = "\n".join((run.stdout or "", run.stderr or ""))
    return {
        line.strip().lower() for line in raw.splitlines()
        if line.strip() and not line.lower().startswith("list of available languages")
    }


def _multilang_negative_ocr(image_path: Path) -> tuple[str, str | None]:
    """OCR browser proof with Korean support without weakening delete policy."""
    binary = shutil.which("tesseract")
    if not binary:
        return "", "tesseract_not_installed"
    languages = _tesseract_languages()
    if "kor" not in languages:
        return "", "korean_tessdata_missing"
    language = "kor+eng" if "eng" in languages else "kor"
    try:
        from PIL import Image, ImageOps
        with Image.open(image_path) as opened:
            source = ImageOps.exif_transpose(opened).convert("RGB")
        width, height = source.size
        regions = (
            ("full", source),
            ("upper72", source.crop((0, 0, width, max(1, int(height * 0.72))))),
            ("upper45", source.crop((0, 0, width, max(1, int(height * 0.45))))),
        )
        chunks: list[str] = []
        with tempfile.TemporaryDirectory(prefix="tcg-negative-proof-") as directory:
            for name, region in regions:
                gray = ImageOps.autocontrast(ImageOps.grayscale(region))
                target_w = max(1400, min(2400, gray.width * 2))
                if gray.width != target_w:
                    ratio = target_w / max(1, gray.width)
                    gray = gray.resize((target_w, max(300, int(gray.height * ratio))))
                file_path = Path(directory) / f"{name}.png"
                gray.save(file_path, format="PNG")
                for psm in (6, 11):
                    run = subprocess.run(
                        [binary, str(file_path), "stdout", "--psm", str(psm), "-l", language],
                        capture_output=True, text=True, encoding="utf-8", errors="replace",
                        timeout=18, check=False,
                    )
                    if run.returncode == 0 and run.stdout.strip():
                        chunks.append(run.stdout.strip())
        text = "\n".join(dict.fromkeys(chunks))
        return text[:8000], None if text else "ocr_empty"
    except ImportError:
        return "", "pillow_not_installed"
    except (OSError, ValueError, subprocess.SubprocessError):
        return "", "multilang_ocr_failed"


'''
replace_once(path, anchor, helper + anchor)

old_submit = '''    signal = _negative_ocr(text, evidence, company)\n    if signal.get("site_error_detected"):\n'''
new_submit = '''    signal = _negative_ocr(text, evidence, company)\n    multilang_error = None\n    if (not signal.get("site_error_detected")\n            and (not signal.get("negative_text_detected") or not signal.get("company_brand_detected"))):\n        extra_text, multilang_error = _multilang_negative_ocr(proof_path)\n        if extra_text:\n            text = "\\n".join(part for part in (text, extra_text) if part)\n            signal = _negative_ocr(text, evidence, company)\n    if signal.get("site_error_detected"):\n'''
replace_once(path, old_submit, new_submit)

old_negative = '''    if not signal.get("negative_text_detected"):\n        proof_path.unlink(missing_ok=True)\n        raise ValueError("공식사이트에 '조회 결과 없음/인증번호 없음' 문구가 확인된 화면만 후보삭제에 사용할 수 있습니다.")\n'''
new_negative = '''    if not signal.get("negative_text_detected"):\n        proof_path.unlink(missing_ok=True)\n        if multilang_error == "korean_tessdata_missing":\n            raise ValueError("한글 공식조회 결과를 읽기 위한 OCR 언어자료가 없습니다. Termux에서 pkg install tesseract-data-kor -y 실행 후 다시 선택하세요.")\n        raise ValueError("공식사이트에 '조회 결과 없음/인증번호 없음' 문구가 확인된 화면만 후보삭제에 사용할 수 있습니다.")\n'''
replace_once(path, old_negative, new_negative)

print("Korean official no-record OCR v171 applied")
# trigger-v171

#!/usr/bin/env python3
from pathlib import Path

proof = Path('manual_official_proof.py')
text = proof.read_text(encoding='utf-8')

if 'import subprocess\n' not in text:
    text = text.replace(
        'import re\nimport threading\nimport time\n',
        'import re\nimport subprocess\nimport tempfile\nimport threading\nimport time\n',
        1,
    )
if 'from PIL import Image, ImageOps\n' not in text:
    text = text.replace(
        'from typing import Any\n\nimport manual_graded_photo_registration as manual_photo\n',
        'from typing import Any\n\nfrom PIL import Image, ImageOps\n\nimport manual_graded_photo_registration as manual_photo\n',
        1,
    )

grade_anchor = '        r"(?:품목\\s*등급|등급)\\s*[:#-]?\\s*(10|[1-9](?:\\.5)?)",\n'
if 'r"\\bMT\\s*(10|8)\\b"' not in text:
    if grade_anchor not in text:
        raise SystemExit('grade pattern anchor not found')
    text = text.replace(
        grade_anchor,
        grade_anchor
        + '        # Android Chrome translation can leave the Latin PSA grade token while GEM is translated.\n'
        + '        # Exact company + certificate matching is still required by _match_proof.\n'
        + '        r"\\bMT\\s*(10|8)\\b",\n',
        1,
    )

function_anchor = '\ndef _match_proof(*, row: dict[str, Any], text: str, evidence: dict[str, Any], company: str, cert: str, expected_grade: float) -> dict[str, Any]:\n'
helper = r'''

def _tesseract_page_pass(image: Image.Image, *, psm: int = 11, digits_only: bool = False) -> tuple[str, str | None]:
    """OCR one official-page viewport pass; optimized for Latin grader tokens and cert digits."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            image.save(tmp.name)
            command = ["tesseract", tmp.name, "stdout", "--psm", str(psm), "-l", "eng"]
            if digits_only:
                command += ["-c", "tessedit_char_whitelist=0123456789"]
            run = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=20,
            )
        if run.returncode != 0:
            return "", f"tesseract_page_exit_{run.returncode}"
        return " ".join(run.stdout.split())[:5000], None
    except FileNotFoundError:
        return "", "tesseract_not_installed"
    except subprocess.TimeoutExpired:
        return "", "tesseract_page_timeout"
    except (OSError, ValueError):
        return "", "official_page_ocr_error"


def _prepare_page_crop(source: Image.Image, top: float, bottom: float, target_width: int) -> Image.Image:
    width, height = source.size
    y0 = max(0, min(height - 1, int(height * top)))
    y1 = max(y0 + 1, min(height, int(height * bottom)))
    crop = source.crop((0, y0, width, y1))
    crop = ImageOps.autocontrast(ImageOps.grayscale(crop))
    scale = max(1.0, float(target_width) / max(1, crop.width))
    size = (max(1, int(crop.width * scale)), max(1, int(crop.height * scale)))
    return crop.resize(size)


def _ocr_official_page(
    image_path: Path, *, expected_company: str = "", expected_cert: str = ""
) -> tuple[str, str | None, dict[str, Any], dict[str, Any]]:
    """OCR a full browser screenshot instead of only the slab-label top crop."""
    base_text, base_error, base_diag, base_evidence = manual_photo._ocr_image(image_path)
    texts = [str(base_text or "")]
    errors = [str(base_error)] if base_error else []
    passes: list[str] = []
    digit_text = ""
    try:
        with Image.open(image_path) as raw:
            source = ImageOps.exif_transpose(raw).convert("RGB")
            variants = (
                ("full_psm11", _prepare_page_crop(source, 0.0, 1.0, 1800), 11, False),
                ("identity_band_psm11", _prepare_page_crop(source, 0.06, 0.72, 2200), 11, False),
                ("lower_grade_psm11", _prepare_page_crop(source, 0.48, 1.0, 2000), 11, False),
                ("identity_digits_psm11", _prepare_page_crop(source, 0.08, 0.74, 2400), 11, True),
            )
            for name, image, psm, digits_only in variants:
                out, err = _tesseract_page_pass(image, psm=psm, digits_only=digits_only)
                passes.append(name)
                if out:
                    texts.append(out)
                    if digits_only:
                        digit_text += " " + out
                if err:
                    errors.append(err)
    except (OSError, ValueError):
        errors.append("official_page_image_open_error")

    combined = " | ".join(dict.fromkeys(part for part in texts if part))[:12000]
    normalized_digits = re.sub(r"\D", "", digit_text)
    expected_cert_clean = _clean_cert(expected_cert)
    cert_seen = bool(
        expected_cert_clean.isdigit()
        and expected_cert_clean
        and expected_cert_clean in normalized_digits
    )
    if cert_seen:
        combined += f" | CERTIFICATION {expected_cert_clean}"

    try:
        from graded_photo_evidence import extract_label_evidence
        evidence = extract_label_evidence(combined)
    except (ImportError, OSError, ValueError, TypeError):
        evidence = dict(base_evidence) if isinstance(base_evidence, dict) else {}

    diagnostics = dict(base_diag) if isinstance(base_diag, dict) else {}
    diagnostics.update({
        "official_page_fullscreen_ocr": True,
        "official_page_passes": passes,
        "expected_company": str(expected_company or "").upper()[:8] or None,
        "expected_cert_seen_in_digit_pass": cert_seen,
        "combined_text_chars": len(combined),
    })
    return (
        combined,
        ";".join(dict.fromkeys(errors)) if errors and not combined else None,
        diagnostics,
        evidence,
    )
'''

if 'def _ocr_official_page(' not in text:
    if function_anchor not in text:
        raise SystemExit('match proof function anchor not found')
    text = text.replace(function_anchor, helper + function_anchor, 1)

old_submit = '    text, ocr_error, diagnostics, evidence = manual_photo._ocr_image(target)\n'
new_submit = (
    '    text, ocr_error, diagnostics, evidence = _ocr_official_page(\n'
    '        target, expected_company=company, expected_cert=cert,\n'
    '    )\n'
)
if old_submit in text:
    text = text.replace(old_submit, new_submit, 1)
elif '_ocr_official_page(\n        target, expected_company=company, expected_cert=cert' not in text:
    raise SystemExit('manual proof submit OCR anchor not found')
proof.write_text(text, encoding='utf-8')

pending = Path('pending_official_candidate_v161.py')
ptext = pending.read_text(encoding='utf-8')
old_pending = '        text, ocr_error, diagnostics, evidence = manual_photo._ocr_image(proof_path)\n'
new_pending = (
    '        text, ocr_error, diagnostics, evidence = manual_proof._ocr_official_page(\n'
    '            proof_path, expected_company=company, expected_cert=cert,\n'
    '        )\n'
)
if old_pending in ptext:
    ptext = ptext.replace(old_pending, new_pending, 1)
elif 'manual_proof._ocr_official_page(' not in ptext:
    raise SystemExit('pending candidate OCR anchor not found')
pending.write_text(ptext, encoding='utf-8')

print('official proof fullscreen OCR v168 applied')

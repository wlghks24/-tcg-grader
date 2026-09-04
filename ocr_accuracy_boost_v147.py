#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OCR accuracy boost for graded-card slab labels.

Goals
-----
- improve company / grade / certification recognition on phone/tablet photos
- keep Tesseract CPU use bounded: one strong first pass, extra passes only if needed
- use grader-specific certification lengths to reject obvious OCR garbage
- treat common OCR substitutions only inside numeric certification candidates
- never change the existing trust model: OCR is evidence, not official grade truth

The patch is process-local and is applied by ``manual_dual_photo_registration``.
It upgrades both manual-upload OCR and the shared slab-corpus OCR helper.
"""
from __future__ import annotations

from collections import Counter
from functools import lru_cache
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

PATCH_ID = 147
ENGINE = "slab-ocr-accuracy-v147"
_APPLIED = False

CERT_LENGTHS = {
    "PSA": (8, 9),
    "CGC": (10, 11, 12, 13),
    "BGS": (9, 10, 11, 12),
    "TAG": (6, 7, 8, 9, 10, 11, 12),
    "BRG": (7,),
}
COMPANIES = tuple(CERT_LENGTHS)

# Conservative OCR-tolerant company markers. These are only used after the
# repository's normal company detector has failed.
_COMPANY_FUZZY = (
    ("PSA", re.compile(r"\bP[S5]A\b|PROFESSIONAL\s+SPORTS\s+AUTHENTICAT", re.I)),
    ("CGC", re.compile(r"\bC[G6]C\b|CERTIFIED\s+GUARANTY", re.I)),
    ("BGS", re.compile(r"\bB[G6]S\b|BECKE[T7]T|BECKETT", re.I)),
    ("TAG", re.compile(r"\bT[A4]G\b|TECHNICAL\s+AUTHENTICATION", re.I)),
    ("BRG", re.compile(r"\bB[R8]G\b|BREAK\s+(?:GRADING|COMPANY)", re.I)),
)

_CERT_MAP = str.maketrans({
    "O": "0", "Q": "0", "D": "0",
    "I": "1", "L": "1", "|": "1",
    "Z": "2", "S": "5", "G": "6", "B": "8",
})


def _norm(text: Any) -> str:
    return " ".join(str(text or "").upper().replace("｜", "|").replace("—", "-").split())


def detect_company(text: str, original=None) -> str | None:
    if callable(original):
        try:
            value = original(text)
            if value in COMPANIES:
                return value
        except (TypeError, ValueError):
            pass
    upper = _norm(text)
    for company, pattern in _COMPANY_FUZZY:
        if pattern.search(upper):
            return company
    return None


def _numericish_to_digits(value: str) -> str:
    raw = re.sub(r"[\s._/#:-]+", "", str(value or "").upper())
    if not raw:
        return ""
    # Do not rewrite arbitrary words. Require the candidate to already be mostly
    # digits / digit-like OCR glyphs.
    allowed = set("0123456789OQDIL|ZSG B")
    meaningful = [ch for ch in raw if ch.isalnum() or ch == "|"]
    if not meaningful:
        return ""
    if sum(ch in allowed for ch in meaningful) / len(meaningful) < 0.78:
        return ""
    mapped = raw.translate(_CERT_MAP)
    return re.sub(r"\D", "", mapped)


def numeric_candidates(text: str) -> list[str]:
    upper = _norm(text)
    patterns = (
        r"(?:CERT(?:IFICATION)?(?:\s*(?:NO|NUMBER|ID))?|CERT#|SERIAL|鑑定番号|인증(?:번호)?)\s*[:#.-]?\s*([0-9OQDIL|ZSG B._ /-]{6,24})",
        r"(?<![A-Z0-9])([0-9OQDIL|ZSG B]{6,13})(?![A-Z0-9])",
        r"(?<![A-Z0-9])((?:[0-9OQDIL|ZSG B]{2,5}[ ._-]){1,4}[0-9OQDIL|ZSG B]{2,5})(?![A-Z0-9])",
    )
    out: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, upper, re.I):
            raw = match.group(1) if match.lastindex else match.group(0)
            digits = _numericish_to_digits(raw)
            if 6 <= len(digits) <= 13 and digits not in out:
                out.append(digits)
    return out


def normalize_cert(company: str | None, text: str) -> str | None:
    if company not in CERT_LENGTHS:
        return None
    allowed = CERT_LENGTHS[company]
    candidates = [value for value in numeric_candidates(text) if len(value) in allowed]
    if not candidates:
        return None
    counts = Counter(candidates)
    # Repetition is strongest; context order is next. Prefer longer only after
    # repetition because a merged grade digit should not beat a repeated cert.
    return max(candidates, key=lambda value: (counts[value], -candidates.index(value), len(value)))


def _grade_number(value: str) -> float | None:
    cleaned = str(value or "").upper().strip().replace(",", ".")
    cleaned = cleaned.replace("I0", "10").replace("L0", "10").replace("IO", "10").replace("LO", "10")
    cleaned = re.sub(r"(?<=\d)\s+(?=5\b)", ".", cleaned)
    try:
        number = float(cleaned)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or number < 1 or number > 10:
        return None
    if abs(number * 2 - round(number * 2)) > 1e-9:
        return None
    return number


def normalize_grade(text: str, company: str | None = None, original=None) -> float | None:
    if callable(original):
        try:
            value = original(text, company)
            if value is not None:
                return float(value)
        except (TypeError, ValueError, OverflowError):
            pass
    upper = _norm(text).replace(",", ".")
    number = r"(10|I0|IO|L0|LO|9(?:[ .]5)?|8(?:[ .]5)?|7(?:[ .]5)?|6(?:[ .]5)?|5(?:[ .]5)?|4(?:[ .]5)?|3(?:[ .]5)?|2(?:[ .]5)?|1(?:[ .]5)?)"
    context = r"(?:FINAL\s*GRADE|OVERALL\s*GRADE|CARD\s*GRADE|ITEM\s*GRADE|GRADE|GEM\s*(?:MT|MINT)|PRISTINE|MINT|NM[ -]*MT)"
    for pattern in (rf"{context}\s*[:#-]?\s*{number}\b", rf"\b{number}\s*{context}\b"):
        match = re.search(pattern, upper, re.I)
        if match:
            for group in reversed(match.groups()):
                grade = _grade_number(group)
                if grade is not None:
                    return grade
    # PSA labels frequently expose the condition word much more clearly than
    # the small grade numeral. Use the published descriptor ordering only as a
    # last OCR fallback and only when PSA itself was identified.
    if company == "PSA":
        descriptor_map = (
            (r"\bGEM\s*MT\b|\bGEM\s*MINT\b", 10.0),
            (r"\bMINT\b", 9.0),
            (r"\bNM[ -]*MT\b", 8.0),
            (r"\bNM\b|NEAR\s+MINT", 7.0),
            (r"\bEX[ -]*MT\b", 6.0),
        )
        for pattern, grade in descriptor_map:
            if re.search(pattern, upper, re.I):
                return grade
    return None


def fields_from_text(text: str, fallback_company: str = "", slab_module=None) -> tuple[str | None, str | None, float | None]:
    original_detector = getattr(slab_module, "_ocr_v147_original_detect_company", None) if slab_module else None
    original_grade = getattr(slab_module, "_ocr_v147_original_normalize_grade", None) if slab_module else None
    visual_company = detect_company(text, original_detector)
    parse_company = visual_company or (str(fallback_company or "").upper() if str(fallback_company or "").upper() in COMPANIES else None)
    cert = normalize_cert(parse_company, text)
    grade = normalize_grade(text, parse_company, original_grade)
    return visual_company, cert, grade


def _otsu_threshold(gray: Image.Image) -> int:
    histogram = gray.histogram()[:256]
    total = sum(histogram) or 1
    sum_total = sum(index * count for index, count in enumerate(histogram))
    weight_bg = 0
    sum_bg = 0
    best = 0.0
    threshold = 165
    for index, count in enumerate(histogram):
        weight_bg += count
        if not weight_bg:
            continue
        weight_fg = total - weight_bg
        if weight_fg <= 0:
            break
        sum_bg += index * count
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_total - sum_bg) / weight_fg
        between = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if between > best:
            best = between
            threshold = index
    return max(90, min(215, threshold))


def _prepare(source: Image.Image, top_fraction: float, target_width: int, mode: str) -> Image.Image:
    width, height = source.size
    # Trim a tiny edge margin: slab borders/reflections often create stronger
    # edges than the label glyphs and hurt segmentation.
    x_margin = max(0, int(width * 0.018))
    crop = source.crop((x_margin, 0, max(x_margin + 1, width - x_margin), max(1, int(height * top_fraction))))
    gray = ImageOps.grayscale(crop)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    ratio = max(1.0, target_width / max(1, gray.width))
    resized = gray.resize((max(target_width, gray.width), max(260, int(gray.height * ratio))), Image.Resampling.LANCZOS)
    resized = resized.filter(ImageFilter.UnsharpMask(radius=1.2, percent=165, threshold=3))
    if mode == "binary":
        t = _otsu_threshold(resized)
        resized = resized.point(lambda p: 255 if p > t else 0)
    elif mode == "contrast":
        resized = ImageEnhance.Contrast(resized).enhance(1.35)
    return resized


@lru_cache(maxsize=1)
def _tesseract_binary() -> str:
    return shutil.which("tesseract") or ""


def _run_tesseract(
    image: Image.Image,
    psm: int,
    *,
    digits_only: bool = False,
    timeout: float = 20.0,
) -> tuple[str, str | None]:
    binary = _tesseract_binary()
    if not binary:
        return "", "tesseract_not_installed"
    command_extra: list[str] = ["-c", "preserve_interword_spaces=1"]
    if digits_only:
        command_extra += ["-c", "tessedit_char_whitelist=0123456789OQDILZSBG|.-/# "]
    bounded_timeout = max(3.0, min(20.0, float(timeout)))
    try:
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            image.save(tmp.name, format="PNG")
            run = subprocess.run(
                [binary, tmp.name, "stdout", "--psm", str(psm), "-l", "eng", *command_extra],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=bounded_timeout, check=False,
            )
        if run.returncode != 0:
            return "", f"tesseract_exit_{run.returncode}"
        return " ".join(run.stdout.split())[:2200], None
    except FileNotFoundError:
        return "", "tesseract_not_installed"
    except subprocess.TimeoutExpired:
        return "", "TimeoutExpired"
    except OSError:
        return "", "tesseract_failed"


def ocr_label(path: Path, profile: str = "accuracy", *, fallback_company: str = "", slab_module=None) -> tuple[str, str | None, dict[str, Any]]:
    """Adaptive multi-crop OCR, stopping as soon as all identity fields resolve."""
    try:
        with Image.open(path) as raw:
            source = ImageOps.exif_transpose(raw).convert("RGB")
            # Ordered by cost/expected yield. Most normal slab photos stop after
            # pass 1 or 2. Difficult glare/crop cases can use all fallbacks.
            if profile == "fast":
                passes = [("top30_gray_psm6", .30, 1500, "gray", 6, False)]
            else:
                passes = [
                    ("top30_gray_psm6", .30, 1700, "gray", 6, False),
                    ("top22_contrast_psm6", .22, 1900, "contrast", 6, False),
                    ("top38_gray_psm11", .38, 1800, "gray", 11, False),
                    ("top30_binary_psm6", .30, 2000, "binary", 6, False),
                    ("top45_binary_psm11", .45, 1900, "binary", 11, False),
                    ("top35_cert_psm11", .35, 2100, "contrast", 11, True),
                ]
            texts: list[str] = []
            errors: list[str] = []
            used: list[str] = []
            fields = (None, None, None)
            started = time.monotonic()
            budget_seconds = 14.0 if profile == "fast" else 48.0
            budget_exhausted = False
            for name, fraction, target_width, mode, psm, digits_only in passes:
                remaining = budget_seconds - (time.monotonic() - started)
                if remaining < 3.0:
                    budget_exhausted = True
                    errors.append("ocr_budget_exhausted")
                    break
                prepared = _prepare(source, fraction, target_width, mode)
                text, error = _run_tesseract(
                    prepared, psm, digits_only=digits_only, timeout=min(20.0, remaining)
                )
                used.append(name)
                if text and text not in texts:
                    texts.append(text)
                if error:
                    errors.append(error)
                combined = " | ".join(texts)
                fields = fields_from_text(combined, fallback_company=fallback_company, slab_module=slab_module)
                visual_company, cert, grade = fields
                company_for_completion = visual_company or (fallback_company if str(fallback_company).upper() in COMPANIES else None)
                if company_for_completion and cert and grade is not None:
                    break
        combined = " | ".join(texts)[:5000]
        visual_company, cert, grade = fields_from_text(combined, fallback_company=fallback_company, slab_module=slab_module)
        score = int(bool(visual_company)) * 34 + int(bool(cert)) * 38 + int(grade is not None) * 28
        error = ";".join(dict.fromkeys(errors)) if errors and not combined else None
        return combined, error, {
            "engine": ENGINE,
            "profile": profile,
            "passes_used": used,
            "pass_count": len(used),
            "company_resolved": visual_company is not None,
            "cert_resolved": cert is not None,
            "grade_resolved": grade is not None,
            "identity_score": score,
            "fallback_company_used_for_parsing": bool(not visual_company and fallback_company),
            "budget_seconds": budget_seconds,
            "budget_exhausted": budget_exhausted,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
    except (OSError, ValueError) as exc:
        return "", type(exc).__name__, {
            "engine": ENGINE, "profile": profile, "passes_used": [], "pass_count": 0,
            "company_resolved": False, "cert_resolved": False, "grade_resolved": False,
            "identity_score": 0,
        }


def _manual_ocr_for_row(row: dict[str, Any]):
    """Manual registration OCR with safe complete-result caching."""
    import manual_graded_photo_registration as manual_photo
    cached = {
        "company": row.get("ocr_company"),
        "grade": row.get("ocr_grade"),
        "certification_id": row.get("ocr_certification_id"),
    }
    if (
        row.get("ocr_cached_sha256") == row.get("image_sha256")
        and cached["company"] and cached["grade"] is not None and cached["certification_id"]
    ):
        diagnostics = row.get("ocr_diagnostics")
        return (
            str(row.get("ocr_label_text") or ""), row.get("ocr_error"),
            dict(diagnostics) if isinstance(diagnostics, dict) else {}, cached, True,
        )
    import library_slab_corpus as slab
    path = manual_photo.ROOT / str(row["image_path"])
    fallback_company = str(row.get("company") or "").upper()
    text, error, diagnostics = ocr_label(path, profile="accuracy", fallback_company=fallback_company, slab_module=slab)
    visual_company, cert, grade = fields_from_text(text, fallback_company=fallback_company, slab_module=slab)
    evidence = {
        "company": visual_company or "",
        "grade": grade,
        "certification_id": cert or "",
        "ocr_text": text[:1200],
    }
    return text, error, diagnostics, evidence, False


def apply() -> dict[str, Any]:
    global _APPLIED
    import library_slab_corpus as slab
    import manual_graded_photo_registration as manual_photo

    if not hasattr(slab, "_ocr_v147_original_detect_company"):
        slab._ocr_v147_original_detect_company = slab.detect_company
    if not hasattr(slab, "_ocr_v147_original_normalize_grade"):
        slab._ocr_v147_original_normalize_grade = slab.normalize_grade
    if not hasattr(slab, "_ocr_v147_original_ocr_label"):
        slab._ocr_v147_original_ocr_label = slab.ocr_label

    slab.detect_company = lambda text: detect_company(text, slab._ocr_v147_original_detect_company)
    slab._numeric_candidates = numeric_candidates
    slab.normalize_cert = normalize_cert
    slab.normalize_grade = lambda text, company=None: normalize_grade(
        text, company, slab._ocr_v147_original_normalize_grade
    )
    slab.ocr_label = lambda path, profile="adaptive": ocr_label(
        path, profile=("fast" if profile == "fast" else "accuracy"), slab_module=slab
    )

    # Override the row-level function so a manually selected grader can guide
    # certification-length parsing without being treated as OCR proof itself.
    manual_photo._ocr_for_row = _manual_ocr_for_row
    _APPLIED = True
    return {
        "ok": True,
        "patch": PATCH_ID,
        "engine": ENGINE,
        "manual_profile": "accuracy",
        "adaptive_multi_crop": True,
        "grader_specific_cert_lengths": True,
        "ocr_confusion_repair": True,
        "manual_claim_used_as_parse_hint_only": True,
        "official_truth_policy_unchanged": True,
    }


def status() -> dict[str, Any]:
    import manual_graded_photo_registration as manual_photo
    return {
        "ok": bool(_APPLIED and manual_photo._ocr_for_row is _manual_ocr_for_row),
        "patch": PATCH_ID,
        "engine": ENGINE,
        "applied": _APPLIED,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(apply(), ensure_ascii=False, indent=2))

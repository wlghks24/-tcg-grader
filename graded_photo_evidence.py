#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bounded image/OCR evidence extraction for public graded-card candidates.

Only fingerprints and short OCR evidence are returned. Image bytes are never
persisted by this module. Network access is HTTPS-only and guarded against
private/loopback destinations and unsafe redirects by ``safe_runtime``.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import io
import math
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any
from urllib.request import Request

from safe_runtime import safe_urlopen, validate_public_https_url

UA = "Mozilla/5.0 TCG-Grader-Verified-Photo-Evidence/4.0"
MAX_IMAGE_BYTES = 8_000_000
MAX_IMAGE_PIXELS = 40_000_000
SUPPORTED_MIME = {"image/jpeg", "image/png", "image/webp"}
COMPANIES = ("PSA", "BGS", "CGC", "TAG", "BRG")

COMPANY_PATTERNS = {
    "PSA": re.compile(r"\bPSA\b", re.I),
    "BGS": re.compile(r"\b(?:BGS|BECKETT)\b", re.I),
    "CGC": re.compile(r"\bCGC\b", re.I),
    "TAG": re.compile(r"\bTAG(?:\s+GRADING)?\b", re.I),
    "BRG": re.compile(r"\bBRG\b|BREAK\s+GRADING", re.I),
}
GRADE_PATTERNS = (
    re.compile(r"\b(?:PSA|BGS|CGC|TAG|BRG|BECKETT)\s*(?:GRADE\s*)?(?:(?:GEM\s*(?:MT|MINT)|PRISTINE|BLACK\s+LABEL|MINT|NM-MT|NEAR\s+MINT)\s*)?(10|9\.5|9|8\.5|8|7\.5|7|6\.5|6|5\.5|5|4\.5|4|3\.5|3|2\.5|2|1\.5|1)\b", re.I),
    re.compile(r"\b(?:FINAL\s+GRADE|CARD\s+GRADE|ITEM\s+GRADE|GRADE)\s*(?:GEM\s*MT|GEM\s*MINT|PRISTINE|MINT|NM-MT)?\s*(10|9\.5|9|8\.5|8|7\.5|7|6\.5|6|5\.5|5|4\.5|4|3\.5|3|2\.5|2|1\.5|1)\b", re.I),
    re.compile(r"(?:등급|그레이드|감정)\s*(10|9\.5|9|8\.5|8|7\.5|7|6\.5|6|5\.5|5|4\.5|4|3\.5|3|2\.5|2|1\.5|1)", re.I),
)
CERT_CONTEXT_RE = re.compile(
    r"(?:CERT(?:IFICATION)?(?:\s*(?:NO|NUMBER))?|인증(?:번호)?|鑑定番号)\s*[:#.-]?\s*([A-Z0-9][A-Z0-9 ./_-]{5,24})",
    re.I,
)


def _company(text: str, fallback: str = "") -> str:
    for company, pattern in COMPANY_PATTERNS.items():
        if pattern.search(text or ""):
            return company
    fallback = str(fallback or "").upper()
    return fallback if fallback in COMPANIES else ""


def _grade(text: str) -> float | None:
    for pattern in GRADE_PATTERNS:
        match = pattern.search(text or "")
        if not match:
            continue
        try:
            grade = float(match.group(1))
        except (TypeError, ValueError):
            continue
        if 1 <= grade <= 10:
            return grade
    return None


def normalize_cert(value: Any) -> str:
    value = re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()
    return value[:24] if 6 <= len(value) <= 24 else ""


def _cert(text: str, company: str, grade: float | None) -> str:
    match = CERT_CONTEXT_RE.search(text or "")
    if match:
        value = normalize_cert(match.group(1).split()[0])
        if value:
            return value
    if not company or grade is None:
        return ""
    # Slab OCR often sees the certification number without its small "CERT" label.
    # Restrict this fallback to company-aware text with a grade and plausible lengths.
    tokens = re.findall(r"(?<![A-Za-z0-9])([A-Z]?\d{7,11})(?![A-Za-z0-9])", text or "", re.I)
    tokens = [normalize_cert(token) for token in tokens]
    tokens = [token for token in tokens if token and not re.fullmatch(r"(?:19|20)\d{6}", token)]
    if company == "TAG":
        tagged = [token for token in tokens if re.fullmatch(r"[A-Z]\d{7}", token)]
        if tagged:
            return tagged[-1]
    return max(tokens, key=len, default="")


def extract_label_evidence(text: str, fallback_company: str = "") -> dict[str, Any]:
    clean = re.sub(r"\s+", " ", str(text or "")).strip()[:5000]
    company = _company(clean, fallback_company)
    grade = _grade(clean)
    cert = _cert(clean, company, grade)
    return {"company": company, "grade": grade, "certification_id": cert, "ocr_text": clean[:1200]}


def _dhash(image) -> str:
    gray = image.convert("L").resize((9, 8))
    pixels = list(gray.getdata())
    value = 0
    for y in range(8):
        for x in range(8):
            value = (value << 1) | int(pixels[y * 9 + x] > pixels[y * 9 + x + 1])
    return f"{value:016x}"


def _ocr(image) -> tuple[str, str | None]:
    binary = shutil.which("tesseract")
    if not binary:
        return "", "tesseract_not_installed"
    width, height = image.size
    # Most slabs place the label in the top quarter. Include a wider top crop and
    # a low-resolution full view so rotated/atypical holders are still readable.
    label = image.crop((0, 0, width, max(1, int(height * 0.38))))
    with tempfile.TemporaryDirectory(prefix="tcg-grade-ocr-") as directory:
        label_path = os.path.join(directory, "label.png")
        full_path = os.path.join(directory, "full.png")
        label.save(label_path, format="PNG")
        full = image.copy()
        full.thumbnail((1400, 2000))
        full.save(full_path, format="PNG")
        chunks: list[str] = []
        try:
            for path, psm in ((label_path, "6"), (label_path, "11"), (full_path, "11")):
                completed = subprocess.run(
                    [binary, path, "stdout", "--psm", psm, "-l", "eng"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=12,
                    check=False,
                )
                if completed.returncode == 0 and completed.stdout.strip():
                    chunks.append(completed.stdout.strip())
        except (OSError, subprocess.SubprocessError):
            return "", "tesseract_failed"
    text = "\n".join(dict.fromkeys(chunks))
    return text[:5000], None if text else "ocr_empty"


def probe_image(url: str, fallback_company: str = "", timeout: int = 10) -> dict[str, Any]:
    result: dict[str, Any] = {"ok": False, "url": str(url or "")[:1200], "bytes_persisted": False}
    try:
        validate_public_https_url(str(url or ""))
        request = Request(
            str(url),
            headers={"User-Agent": UA, "Accept": "image/avif,image/webp,image/png,image/jpeg;q=0.9,*/*;q=0.1"},
        )
        with safe_urlopen(request, timeout=max(3, min(int(timeout), 15)), max_redirects=3) as response:
            content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            raw = response.read(MAX_IMAGE_BYTES + 1)
        if len(raw) > MAX_IMAGE_BYTES:
            return {**result, "error": "image_too_large"}
        if content_type not in SUPPORTED_MIME:
            return {**result, "error": "unsupported_image_mime", "content_type": content_type}
        from PIL import Image, ImageOps

        Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
        with Image.open(io.BytesIO(raw)) as opened:
            opened.verify()
        with Image.open(io.BytesIO(raw)) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
        width, height = image.size
        if width < 180 or height < 220 or width * height > MAX_IMAGE_PIXELS:
            return {**result, "error": "invalid_image_dimensions", "width": width, "height": height}
        ocr_text, ocr_error = _ocr(image)
        evidence = extract_label_evidence(ocr_text, fallback_company)
        return {
            **result,
            "ok": True,
            "content_type": content_type,
            "byte_count": len(raw),
            "width": width,
            "height": height,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "perceptual_hash": _dhash(image),
            "ocr_error": ocr_error,
            "ocr_company": evidence["company"],
            "ocr_grade": evidence["grade"],
            "ocr_certification_id": evidence["certification_id"],
            "ocr_text": evidence["ocr_text"],
        }
    except ImportError:
        return {**result, "error": "pillow_not_installed"}
    except (OSError, ValueError, TypeError, TimeoutError) as exc:
        return {**result, "error": type(exc).__name__}


def _merge_probe(row: dict[str, Any], probe: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["image_probe_status"] = "validated" if probe.get("ok") else "failed"
    if not probe.get("ok"):
        item["image_probe_error"] = str(probe.get("error") or "unknown")[:80]
        return item
    item.update(
        {
            "image_validated": True,
            "image_sha256": probe.get("sha256"),
            "image_perceptual_hash": probe.get("perceptual_hash"),
            "image_width": probe.get("width"),
            "image_height": probe.get("height"),
            "ocr_error": probe.get("ocr_error"),
            "ocr_label_text": str(probe.get("ocr_text") or "")[:1200],
        }
    )
    conflicts: list[str] = []
    ocr_company = str(probe.get("ocr_company") or "")
    ocr_grade = probe.get("ocr_grade")
    ocr_cert = normalize_cert(probe.get("ocr_certification_id"))
    old_company = str(item.get("company") or "")
    old_grade = item.get("grade")
    old_cert = normalize_cert(item.get("certification_id"))
    if old_company and ocr_company and old_company != ocr_company:
        conflicts.append("company_conflict")
    elif ocr_company:
        item["company"] = ocr_company
        item["company_evidence"] = "image_ocr"
    if old_grade is not None and ocr_grade is not None:
        try:
            old_value = float(old_grade)
            if not math.isfinite(old_value) or abs(old_value - float(ocr_grade)) > 1e-9:
                conflicts.append("grade_conflict")
        except (TypeError, ValueError, OverflowError):
            conflicts.append("grade_value_invalid")
    elif ocr_grade is not None:
        item["grade"] = float(ocr_grade)
        item["grade_evidence"] = "image_ocr"
    if old_cert and ocr_cert and old_cert != ocr_cert:
        conflicts.append("certification_conflict")
    elif ocr_cert:
        item["certification_id"] = ocr_cert
        item["certification_evidence"] = "image_ocr"
    if conflicts:
        existing = item.get("evidence_conflicts") if isinstance(item.get("evidence_conflicts"), list) else []
        item["evidence_conflicts"] = sorted(set(str(value) for value in existing + conflicts if value))
    return item


def enrich_rows(rows: list[dict[str, Any]], limit: int = 12, workers: int = 3) -> tuple[list[dict[str, Any]], dict[str, int]]:
    limit = max(0, min(int(limit), 40))
    selected: list[tuple[int, dict[str, Any]]] = []
    seen_urls: set[str] = set()
    priorities = sorted(
        enumerate(rows),
        key=lambda pair: (
            not bool(pair[1].get("image_url")),
            bool(pair[1].get("certification_id")) and pair[1].get("grade") is not None,
            -_safe_source_weight(pair[1].get("source_weight", 0)),
        ),
    )
    for index, row in priorities:
        url = str(row.get("image_url") or "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        selected.append((index, row))
        if len(selected) >= limit:
            break
    probes: dict[int, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(int(workers), 4)), thread_name_prefix="grade-photo-ocr") as pool:
        future_map = {
            pool.submit(probe_image, str(row.get("image_url") or ""), str(row.get("company") or "")): index
            for index, row in selected
        }
        for future, index in list((future, index) for future, index in future_map.items()):
            try:
                probes[index] = future.result(timeout=45)
            except Exception as exc:
                probes[index] = {"ok": False, "error": type(exc).__name__}
    output = [_merge_probe(row, probes[index]) if index in probes else dict(row) for index, row in enumerate(rows)]
    return output, {
        "attempted": len(selected),
        "validated": sum(bool(probe.get("ok")) for probe in probes.values()),
        "ocr_readable": sum(bool(probe.get("ocr_text")) for probe in probes.values()),
        "certs_extracted": sum(bool(probe.get("ocr_certification_id")) for probe in probes.values()),
        "failed": sum(not bool(probe.get("ok")) for probe in probes.values()),
    }


def _safe_source_weight(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return number if math.isfinite(number) else 0.0

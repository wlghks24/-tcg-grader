#!/usr/bin/env python3
"""Build a quarantine-first corpus from third-party graded-card photos.

The importer never treats text printed on a slab as an official result. A row
is eligible for the verified corpus only when an independently maintained
official registry matches company, certification number, and grade exactly.
Raw-card calibration data is intentionally never written by this module.

Nested directories are scanned recursively so large training archives can keep
their original folder structure. Progress is printed periodically because OCR
on thousands of slab images can take a long time on mobile devices.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

COMPANIES = ("PSA", "BGS", "CGC", "TAG", "BRG")
IMAGE_SUFFIXES = {
    ".jpg", ".jpeg", ".jfif", ".png", ".webp", ".heic",
    ".bmp", ".tif", ".tiff",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_images(input_dir: Path) -> list[Path]:
    """Return supported images below input_dir, including every nested folder."""
    if not input_dir.exists():
        raise FileNotFoundError(f"input directory does not exist: {input_dir}")
    if not input_dir.is_dir():
        raise NotADirectoryError(f"input path is not a directory: {input_dir}")
    return sorted(
        (path for path in input_dir.rglob("*")
         if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES),
        key=lambda path: str(path).casefold(),
    )


def relative_name(path: Path, input_dir: Path) -> str:
    try:
        return path.relative_to(input_dir).as_posix()
    except ValueError:
        return path.name


def detect_company(text: str) -> str | None:
    upper = text.upper()
    if re.search(r"\bPSA\b|PROFESSIONAL SPORTS AUTHENTICATOR", upper):
        return "PSA"
    if re.search(r"\bCGC\b|CERTIFIED GUARANTY", upper):
        return "CGC"
    if re.search(r"\bBGS\b|BECKETT", upper):
        return "BGS"
    if re.search(r"\b[A-Z]?BRG\b|BREAK\s*&\s*COMPANY", upper):
        return "BRG"
    if re.search(r"TECHNICAL AUTHENTICATION|\bTAG\s+(?:GRADING|DIG)\b", upper):
        return "TAG"
    repeated = Counter(re.findall(r"(?<!\d)\d{8,9}(?!\d)", upper))
    if "GEM MT" in upper and any(count >= 2 for count in repeated.values()):
        return "PSA"
    return None


def normalize_cert(company: str | None, text: str) -> str | None:
    if not company:
        return None
    compact = text.upper().replace("O", "0")
    candidates = re.findall(r"(?<!\d)\d[\d\s.-]{4,16}\d(?!\d)", compact)
    digits = [re.sub(r"\D", "", value) for value in candidates]
    allowed = {
        "PSA": (8, 9),
        "CGC": (10, 11, 12, 13),
        "BGS": (9, 10, 11, 12),
        "TAG": (6, 7, 8, 9, 10, 11, 12),
        "BRG": (7,),
    }[company]
    candidates = [value for value in digits if len(value) in allowed]
    if not candidates:
        return None
    max_len = max(map(len, candidates))
    return [value for value in candidates if len(value) == max_len][-1]


def normalize_grade(text: str) -> float | None:
    upper = text.upper().replace(",", ".")
    patterns = (
        r"(?:GEM\s*MT|GEM\s*MINT|PRISTINE|MINT|NM[\s-]*MT|EXCELLENT|GRADE)\s*[:#-]?\s*(10|9\.5|9|8\.5|8|7\.5|7|6\.5|6|5\.5|5|4\.5|4|3\.5|3|2\.5|2|1\.5|1)\b",
        r"\b(10|9\.5|9|8\.5|8|7\.5|7|6\.5|6|5\.5|5|4\.5|4|3\.5|3|2\.5|2|1\.5|1)\s*(?:GEM\s*MT|GEM\s*MINT|PRISTINE|MINT|NM[\s-]*MT)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, upper)
        if match:
            return float(match.group(1))
    if "GEM MT" in upper:
        return 10.0
    return None


def dhash(path: Path) -> str | None:
    try:
        with Image.open(path) as image:
            gray = ImageOps.grayscale(image).resize((9, 8))
            pixels = list(gray.get_flattened_data())
        bits = 0
        for row in range(8):
            for col in range(8):
                bits = (bits << 1) | (pixels[row * 9 + col] > pixels[row * 9 + col + 1])
        return f"{bits:016x}"
    except (OSError, ValueError):
        return None


def ocr_label(path: Path) -> tuple[str, str | None]:
    try:
        with Image.open(path) as source:
            source = ImageOps.exif_transpose(source).convert("RGB")
            width, height = source.size
            crop = source.crop((0, 0, width, max(1, int(height * 0.42))))
            crop = ImageOps.autocontrast(ImageOps.grayscale(crop)).resize(
                (max(900, width * 2), max(360, int(height * 0.84)))
            )
            with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
                crop.save(tmp.name)
                run = subprocess.run(
                    ["tesseract", tmp.name, "stdout", "--psm", "6", "-l", "eng"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=30,
                )
        if run.returncode != 0:
            return "", f"tesseract_exit_{run.returncode}"
        return " ".join(run.stdout.split())[:1200], None
    except FileNotFoundError:
        return "", "tesseract_not_installed"
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        return "", type(exc).__name__


def load_registry(path: Path | None) -> dict[tuple[str, str], dict[str, Any]]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("certifications", []) if isinstance(payload, dict) else []
    registry: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        company = str(row.get("company", "")).upper()
        cert = re.sub(r"\D", "", str(row.get("certification_id", "")))
        if company in COMPANIES and cert and row.get("officially_verified") is True:
            registry[(company, cert)] = row
    return registry


def load_reviewed_overrides(path: Path | None) -> dict[str, str]:
    if path is None or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("reviewed_company_labels", []) if isinstance(payload, dict) else []
    out: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("source_name", "")).replace("\\", "/")
        company = str(row.get("company", "")).upper()
        if name and company in COMPANIES and row.get("visual_reviewed") is True:
            out[name] = company
    return out


def build(
    input_dir: Path,
    official_registry: Path | None = None,
    reviewed_overrides: Path | None = None,
    *,
    progress_every: int = 50,
) -> tuple[dict[str, Any], dict[str, Any]]:
    registry = load_registry(official_registry)
    overrides = load_reviewed_overrides(reviewed_overrides)
    paths = iter_images(input_dir)
    total = len(paths)
    print(json.dumps({
        "input_dir": str(input_dir),
        "recursive_image_files_found": total,
        "official_registry_entries": len(registry),
    }, ensure_ascii=False), flush=True)

    seen_hashes: dict[str, str] = {}
    records: list[dict[str, Any]] = []

    for index, path in enumerate(paths, start=1):
        source_name = relative_name(path, input_dir)
        if progress_every > 0 and (index == 1 or index % progress_every == 0 or index == total):
            print(f"[slab-scan] {index}/{total} ({index * 100 / max(total, 1):.1f}%) {source_name}", flush=True)

        try:
            size = path.stat().st_size
            digest = sha256_file(path)
        except OSError as exc:
            records.append({
                "source_name": source_name,
                "sha256": None,
                "bytes": 0,
                "perceptual_hash": None,
                "exact_duplicate_of": None,
                "company": None,
                "company_classification_source": None,
                "certification_id": None,
                "label_grade": None,
                "mode": "slab",
                "ocr_label_text": "",
                "ocr_error": type(exc).__name__,
                "official_result": False,
                "status": "quarantine",
                "quarantine_reasons": ["file_read_error"],
                "official_reference_url": None,
            })
            continue

        exact_duplicate_of = seen_hashes.get(digest)
        if exact_duplicate_of is None and size:
            seen_hashes[digest] = source_name

        text, ocr_error = (
            ocr_label(path)
            if size and exact_duplicate_of is None
            else ("", "exact_duplicate_skipped" if size else "empty_file")
        )
        company = detect_company(text)
        classification_source = "ocr" if company else None
        override_company = overrides.get(source_name) or overrides.get(path.name)
        if company is None and override_company:
            company = override_company
            classification_source = "visual_review_candidate_only"

        cert = normalize_cert(company, text)
        grade = normalize_grade(text)
        registry_row = registry.get((company, cert)) if company and cert else None
        official_match = bool(
            registry_row
            and grade is not None
            and abs(float(registry_row.get("grade")) - grade) < 1e-9
        )
        status = "verified" if official_match else "quarantine"
        reasons: list[str] = []
        if not size:
            reasons.append("empty_file")
        if exact_duplicate_of:
            reasons.append("exact_duplicate")
        if ocr_error and ocr_error not in ("exact_duplicate_skipped",):
            reasons.append("ocr_or_image_error")
        if company is None:
            reasons.append("company_unresolved")
        if cert is None:
            reasons.append("certification_unresolved")
        if grade is None:
            reasons.append("grade_unresolved")
        if company and cert and registry_row is None:
            reasons.append("official_lookup_not_confirmed")
        if registry_row and grade is not None and not official_match:
            reasons.append("official_grade_conflict")

        records.append({
            "source_name": source_name,
            "sha256": digest,
            "bytes": size,
            "perceptual_hash": dhash(path) if size and exact_duplicate_of is None else None,
            "exact_duplicate_of": exact_duplicate_of,
            "company": company,
            "company_classification_source": classification_source,
            "certification_id": cert,
            "label_grade": grade,
            "mode": "slab",
            "ocr_label_text": text,
            "ocr_error": ocr_error,
            "official_result": official_match,
            "status": status,
            "quarantine_reasons": reasons,
            "official_reference_url": registry_row.get("official_reference_url") if official_match else None,
        })

    by_cert: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        if row.get("company") and row.get("certification_id"):
            by_cert[(row["company"], row["certification_id"])].append(row)

    conflicts = []
    for (company, cert), rows in by_cert.items():
        grades = sorted({row["label_grade"] for row in rows if row["label_grade"] is not None})
        if len(grades) > 1:
            conflicts.append({"company": company, "certification_id": cert, "label_grades": grades})
            for row in rows:
                row["status"] = "quarantine"
                row["official_result"] = False
                row["quarantine_reasons"] = sorted(
                    set(row["quarantine_reasons"] + ["same_cert_conflicting_grades"])
                )

    verified = []
    emitted: set[tuple[str, str]] = set()
    for row in records:
        key = (row.get("company"), row.get("certification_id"))
        if row.get("official_result") and key not in emitted:
            reg = registry[key]
            verified.append({
                "company": row["company"],
                "certification_id": row["certification_id"],
                "official_grade": float(reg["grade"]),
                "card_name": reg.get("card_name"),
                "game": reg.get("game", "unknown"),
                "mode": "slab",
                "official_result": True,
                "official_reference_url": reg["official_reference_url"],
                "source_sha256": row["sha256"],
                "source_name": row["source_name"],
                "learning_eligibility": "reference_only_missing_raw_prediction",
            })
            emitted.add(key)

    summary = {
        "files_scanned": len(records),
        "nonempty_files": sum(int(row.get("bytes") or 0) > 0 for row in records),
        "unique_exact_images": len({row.get("sha256") for row in records if row.get("sha256")}),
        "exact_duplicate_files": sum(row.get("exact_duplicate_of") is not None for row in records),
        "company_detected_files": sum(row.get("company") is not None for row in records),
        "certification_detected_files": sum(row.get("certification_id") is not None for row in records),
        "officially_verified_certifications": len(verified),
        "company_counts": dict(sorted(Counter(row["company"] for row in records if row.get("company")).items())),
        "quarantined_files": sum(row.get("status") == "quarantine" for row in records),
        "recursive_scan": True,
    }

    manifest = {
        "schema_version": 2,
        "created_at": utc_now(),
        "source_scope": "recursive_user_training_inbox",
        "input_dir": str(input_dir),
        "records": records,
        "conflicting_certifications": conflicts,
        "summary": summary,
        "policy": {
            "seller_or_slab_label_alone_is_official": False,
            "official_registry_match_required": True,
            "raw_and_slab_learning_isolated": True,
            "raw_calibration_modified": False,
            "verified_photo_without_raw_prediction_is_reference_only": True,
        },
    }
    verified_payload = {
        "schema_version": 2,
        "created_at": manifest["created_at"],
        "certifications": verified,
        "training_rows_written": 0,
        "reason": "Slab references lack an independent raw-camera prediction; importing them into raw calibration would create leakage.",
    }
    return manifest, verified_payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--official-registry", type=Path)
    parser.add_argument("--reviewed-overrides", type=Path)
    parser.add_argument("--manifest", type=Path, default=Path("library_slab_candidates.json"))
    parser.add_argument("--verified", type=Path, default=Path("library_verified_slab_references.json"))
    parser.add_argument("--progress-every", type=int, default=50)
    args = parser.parse_args()

    manifest, verified = build(
        args.input_dir,
        args.official_registry,
        args.reviewed_overrides,
        progress_every=max(0, args.progress_every),
    )
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.verified.write_text(json.dumps(verified, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest["summary"], ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

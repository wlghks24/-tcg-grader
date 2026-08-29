#!/usr/bin/env python3
"""Build a quarantine-first corpus from third-party graded-card photos.

Safety rules:
- Seller/slab text alone is never treated as an official grade.
- Official verification requires company + certification number + grade to match
  an independently maintained official registry row.
- Raw-card calibration data is never modified by this module.
- Exact duplicate images inherit OCR/classification from the first identical
  image, avoiding both wasted OCR and false "unresolved" counts.

The OCR pipeline is adaptive. It starts with one fast label pass and only runs
additional crops / page-segmentation modes when company, certification number,
or grade are still unresolved. Use --sample-size for a quick tablet benchmark
before scanning the full archive.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
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
CERT_LENGTHS = {
    "PSA": (8, 9),
    "CGC": (10, 11, 12, 13),
    "BGS": (9, 10, 11, 12),
    "TAG": (6, 7, 8, 9, 10, 11, 12),
    "BRG": (7,),
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


def choose_paths(paths: list[Path], sample_size: int, sample_seed: int) -> list[Path]:
    """Choose a stable random sample without biasing toward one seller/source folder."""
    if sample_size <= 0 or sample_size >= len(paths):
        return paths
    picked = random.Random(sample_seed).sample(paths, sample_size)
    return sorted(picked, key=lambda path: str(path).casefold())


def relative_name(path: Path, input_dir: Path) -> str:
    try:
        return path.relative_to(input_dir).as_posix()
    except ValueError:
        return path.name


def _normalized_ocr(text: str) -> str:
    return " ".join(text.upper().replace("｜", "|").split())


def detect_company(text: str) -> str | None:
    upper = _normalized_ocr(text)

    if re.search(r"\bPSA\b|PROFESSIONAL\s+SPORTS\s+AUTHENTICATOR", upper):
        return "PSA"
    if re.search(r"\bCGC\b|CERTIFIED\s+GUARANTY", upper):
        return "CGC"
    if re.search(r"\bBGS\b|BECKETT(?:\s+GRADING|\s+AUTHENTICATION)?", upper):
        return "BGS"
    if re.search(r"\bBRG\b|BREAK\s*(?:&|AND)\s*COMPANY|BREAK\s+GRADING", upper):
        return "BRG"
    if re.search(
        r"TECHNICAL\s+AUTHENTICATION(?:\s+AND|\s*&)?\s+GRADING"
        r"|\bTAG\s+(?:GRADING|DIG|AUTHENTICATION)\b",
        upper,
    ):
        return "TAG"

    repeated = Counter(re.findall(r"(?<!\d)\d{8,9}(?!\d)", upper))
    if re.search(r"\b(?:GEM\s*MT|MINT|NM[\s-]*MT)\b", upper) and any(
        count >= 2 for count in repeated.values()
    ):
        return "PSA"
    return None


def _numeric_candidates(text: str) -> list[str]:
    compact = _normalized_ocr(text)
    patterns = (
        r"(?<![A-Z0-9])[0-9OQDIL]{6,13}(?![A-Z0-9])",
        r"(?<![A-Z0-9])(?:[0-9OQDIL]{2,4}[ -]){1,4}[0-9OQDIL]{2,4}(?![A-Z0-9])",
        r"(?:CERT(?:IFICATION)?(?:\s*(?:NO|NUMBER))?\s*[:#-]?\s*)([0-9OQDIL .-]{6,20})",
    )
    values: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, compact):
            value = match.group(1) if match.lastindex else match.group(0)
            mapped = value.translate(
                str.maketrans({"O": "0", "Q": "0", "D": "0", "I": "1", "L": "1"})
            )
            digits = re.sub(r"\D", "", mapped)
            if 6 <= len(digits) <= 13:
                values.append(digits)
    return list(dict.fromkeys(values))


def normalize_cert(company: str | None, text: str) -> str | None:
    if not company:
        return None
    allowed = CERT_LENGTHS[company]
    candidates = [value for value in _numeric_candidates(text) if len(value) in allowed]
    if not candidates:
        return None

    counts = Counter(candidates)
    return max(
        candidates,
        key=lambda value: (counts[value], len(value), candidates.index(value)),
    )


def normalize_grade(text: str, company: str | None = None) -> float | None:
    upper = _normalized_ocr(text).replace(",", ".")
    number = r"(10|9\.5|9|8\.5|8|7\.5|7|6\.5|6|5\.5|5|4\.5|4|3\.5|3|2\.5|2|1\.5|1)"
    descriptors = r"(?:GEM\s*MT|GEM\s*MINT|PRISTINE|MINT|NM[\s-]*MT|EXCELLENT|GRADE)"
    patterns = (
        rf"{descriptors}\s*[:#-]?\s*{number}\b",
        rf"\b{number}\s*{descriptors}\b",
        rf"\bGRADE\s*[:#-]?\s*{number}\b",
    )
    for pattern in patterns:
        match = re.search(pattern, upper)
        if match:
            for group in match.groups():
                if group and re.fullmatch(number, group):
                    return float(group)

    if company == "PSA" and re.search(r"\bGEM\s*MT\b", upper):
        return 10.0
    if company in {"BGS", "CGC", "TAG", "BRG"}:
        match = re.search(r"\b(?:FINAL\s+GRADE|OVERALL\s+GRADE|GRADE)\s*[:#-]?\s*" + number + r"\b", upper)
        if match:
            return float(match.group(1))
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


def _prepare_crop(source: Image.Image, top_fraction: float, scale: float, threshold: bool) -> Image.Image:
    width, height = source.size
    crop = source.crop((0, 0, width, max(1, int(height * top_fraction))))
    crop = ImageOps.autocontrast(ImageOps.grayscale(crop))
    if threshold:
        crop = crop.point(lambda p: 255 if p > 172 else 0)
    target_w = max(900, int(width * scale))
    ratio = target_w / max(1, crop.width)
    target_h = max(300, int(crop.height * ratio))
    return crop.resize((target_w, target_h))


def _run_tesseract(image: Image.Image, psm: int) -> tuple[str, str | None]:
    try:
        with tempfile.NamedTemporaryFile(suffix=".png") as tmp:
            image.save(tmp.name)
            run = subprocess.run(
                ["tesseract", tmp.name, "stdout", "--psm", str(psm), "-l", "eng"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )
        if run.returncode != 0:
            return "", f"tesseract_exit_{run.returncode}"
        return " ".join(run.stdout.split())[:1800], None
    except FileNotFoundError:
        return "", "tesseract_not_installed"
    except subprocess.TimeoutExpired:
        return "", "TimeoutExpired"


def _fields_from_text(text: str) -> tuple[str | None, str | None, float | None]:
    company = detect_company(text)
    cert = normalize_cert(company, text)
    grade = normalize_grade(text, company)
    return company, cert, grade


def ocr_label(path: Path, profile: str = "adaptive") -> tuple[str, str | None, dict[str, Any]]:
    """OCR slab label using a fast first pass and adaptive fallbacks."""
    try:
        with Image.open(path) as raw:
            source = ImageOps.exif_transpose(raw).convert("RGB")
            passes = [
                ("top42_psm6", 0.42, 2.0, False, 6),
            ]
            if profile == "adaptive":
                passes += [
                    ("top30_psm6", 0.30, 2.8, False, 6),
                    ("top50_psm11", 0.50, 2.4, False, 11),
                    ("top38_bin_psm11", 0.38, 3.0, True, 11),
                ]

            texts: list[str] = []
            errors: list[str] = []
            used: list[str] = []
            for name, fraction, scale, threshold, psm in passes:
                crop = _prepare_crop(source, fraction, scale, threshold)
                text, error = _run_tesseract(crop, psm)
                used.append(name)
                if text:
                    texts.append(text)
                if error:
                    errors.append(error)

                combined = " | ".join(texts)
                company, cert, grade = _fields_from_text(combined)
                if profile == "adaptive" and company and cert and grade is not None:
                    break

        combined = " | ".join(dict.fromkeys(texts))[:5000]
        error = ";".join(dict.fromkeys(errors)) if errors and not combined else None
        company, cert, grade = _fields_from_text(combined)
        return combined, error, {
            "profile": profile,
            "passes_used": used,
            "pass_count": len(used),
            "company_resolved": company is not None,
            "cert_resolved": cert is not None,
            "grade_resolved": grade is not None,
        }
    except (OSError, ValueError) as exc:
        return "", type(exc).__name__, {
            "profile": profile,
            "passes_used": [],
            "pass_count": 0,
            "company_resolved": False,
            "cert_resolved": False,
            "grade_resolved": False,
        }


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


def _clone_duplicate_fields(original: dict[str, Any], source_name: str, size: int, digest: str) -> dict[str, Any]:
    """Reuse OCR fields for byte-identical images without claiming extra evidence."""
    reasons = [reason for reason in original.get("quarantine_reasons", []) if reason != "file_read_error"]
    reasons = sorted(set(reasons + ["exact_duplicate"]))
    return {
        "source_name": source_name,
        "sha256": digest,
        "bytes": size,
        "perceptual_hash": original.get("perceptual_hash"),
        "exact_duplicate_of": original.get("source_name"),
        "company": original.get("company"),
        "company_classification_source": (
            "exact_duplicate_inherited" if original.get("company") else None
        ),
        "certification_id": original.get("certification_id"),
        "label_grade": original.get("label_grade"),
        "mode": "slab",
        "ocr_label_text": original.get("ocr_label_text", ""),
        "ocr_error": "exact_duplicate_inherited",
        "ocr_diagnostics": {
            "profile": "inherited",
            "passes_used": [],
            "pass_count": 0,
            "company_resolved": original.get("company") is not None,
            "cert_resolved": original.get("certification_id") is not None,
            "grade_resolved": original.get("label_grade") is not None,
        },
        "official_result": bool(original.get("official_result")),
        "status": original.get("status", "quarantine"),
        "quarantine_reasons": reasons,
        "official_reference_url": original.get("official_reference_url"),
    }


def build(
    input_dir: Path,
    official_registry: Path | None = None,
    reviewed_overrides: Path | None = None,
    *,
    progress_every: int = 50,
    sample_size: int = 0,
    sample_seed: int = 20260830,
    ocr_profile: str = "adaptive",
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    registry = load_registry(official_registry)
    overrides = load_reviewed_overrides(reviewed_overrides)
    all_paths = iter_images(input_dir)
    paths = choose_paths(all_paths, sample_size, sample_seed)
    total = len(paths)
    print(json.dumps({
        "input_dir": str(input_dir),
        "recursive_image_files_found": len(all_paths),
        "selected_files": total,
        "sample_size": sample_size if sample_size > 0 else None,
        "sample_seed": sample_seed if sample_size > 0 else None,
        "ocr_profile": ocr_profile,
        "official_registry_entries": len(registry),
    }, ensure_ascii=False), flush=True)

    seen_hashes: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []

    for index, path in enumerate(paths, start=1):
        source_name = relative_name(path, input_dir)
        if progress_every > 0 and (index == 1 or index % progress_every == 0 or index == total):
            print(
                f"[slab-scan] {index}/{total} ({index * 100 / max(total, 1):.1f}%) {source_name}",
                flush=True,
            )

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
                "ocr_diagnostics": {"profile": ocr_profile, "passes_used": [], "pass_count": 0},
                "official_result": False,
                "status": "quarantine",
                "quarantine_reasons": ["file_read_error"],
                "official_reference_url": None,
            })
            continue

        original = seen_hashes.get(digest)
        if original is not None and size:
            duplicate = _clone_duplicate_fields(original, source_name, size, digest)
            records.append(duplicate)
            continue

        if not size:
            text, ocr_error, diagnostics = "", "empty_file", {
                "profile": ocr_profile,
                "passes_used": [],
                "pass_count": 0,
                "company_resolved": False,
                "cert_resolved": False,
                "grade_resolved": False,
            }
        else:
            text, ocr_error, diagnostics = ocr_label(path, profile=ocr_profile)

        company = detect_company(text)
        classification_source = "ocr" if company else None
        override_company = overrides.get(source_name) or overrides.get(path.name)
        if company is None and override_company:
            company = override_company
            classification_source = "visual_review_candidate_only"

        cert = normalize_cert(company, text)
        grade = normalize_grade(text, company)
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
        if ocr_error:
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

        row = {
            "source_name": source_name,
            "sha256": digest,
            "bytes": size,
            "perceptual_hash": dhash(path) if size else None,
            "exact_duplicate_of": None,
            "company": company,
            "company_classification_source": classification_source,
            "certification_id": cert,
            "label_grade": grade,
            "mode": "slab",
            "ocr_label_text": text,
            "ocr_error": ocr_error,
            "ocr_diagnostics": diagnostics,
            "official_result": official_match,
            "status": status,
            "quarantine_reasons": reasons,
            "official_reference_url": registry_row.get("official_reference_url") if official_match else None,
        }
        records.append(row)
        if size:
            seen_hashes[digest] = row

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

    queue_rows = []
    queued: set[tuple[str, str]] = set()
    for row in records:
        company = row.get("company")
        cert = row.get("certification_id")
        if not company or not cert:
            continue
        key = (company, cert)
        if key in registry or key in queued:
            continue
        queue_rows.append({
            "company": company,
            "certification_id": cert,
            "label_grade_candidate": row.get("label_grade"),
            "source_name": row.get("source_name"),
            "source_sha256": row.get("sha256"),
            "status": "official_lookup_required",
            "training_eligible": False,
        })
        queued.add(key)

    unique_rows = [row for row in records if row.get("exact_duplicate_of") is None]
    summary = {
        "files_scanned": len(records),
        "nonempty_files": sum(int(row.get("bytes") or 0) > 0 for row in records),
        "unique_exact_images": len({row.get("sha256") for row in records if row.get("sha256")}),
        "exact_duplicate_files": sum(row.get("exact_duplicate_of") is not None for row in records),
        "company_detected_files": sum(row.get("company") is not None for row in records),
        "certification_detected_files": sum(row.get("certification_id") is not None for row in records),
        "grade_detected_files": sum(row.get("label_grade") is not None for row in records),
        "unique_company_detected_files": sum(row.get("company") is not None for row in unique_rows),
        "unique_certification_detected_files": sum(row.get("certification_id") is not None for row in unique_rows),
        "unique_grade_detected_files": sum(row.get("label_grade") is not None for row in unique_rows),
        "officially_verified_certifications": len(verified),
        "official_verification_queue": len(queue_rows),
        "company_counts": dict(sorted(Counter(
            row["company"] for row in unique_rows if row.get("company")
        ).items())),
        "quarantined_files": sum(row.get("status") == "quarantine" for row in records),
        "ocr_passes_total": sum(int(row.get("ocr_diagnostics", {}).get("pass_count", 0)) for row in unique_rows),
        "recursive_scan": True,
        "sampled": sample_size > 0 and sample_size < len(all_paths),
        "ocr_profile": ocr_profile,
    }

    manifest = {
        "schema_version": 3,
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
            "duplicate_ocr_is_inherited_not_recomputed": True,
        },
    }
    verified_payload = {
        "schema_version": 3,
        "created_at": manifest["created_at"],
        "certifications": verified,
        "training_rows_written": 0,
        "reason": (
            "Slab references lack an independent raw-camera prediction; importing "
            "them into raw calibration would create leakage."
        ),
    }
    queue_payload = {
        "schema_version": 1,
        "created_at": manifest["created_at"],
        "records": queue_rows,
        "training_rows_written": 0,
        "policy": "Official company lookup required before any row may be verified.",
    }
    return manifest, verified_payload, queue_payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("--official-registry", type=Path)
    parser.add_argument("--reviewed-overrides", type=Path)
    parser.add_argument("--manifest", type=Path, default=Path("library_slab_candidates.json"))
    parser.add_argument("--verified", type=Path, default=Path("library_verified_slab_references.json"))
    parser.add_argument(
        "--verification-queue",
        type=Path,
        default=Path("library_cert_verification_queue.json"),
    )
    parser.add_argument("--progress-every", type=int, default=50)
    parser.add_argument(
        "--sample-size",
        type=int,
        default=0,
        help="Stable random sample size; 0 scans all images.",
    )
    parser.add_argument("--sample-seed", type=int, default=20260830)
    parser.add_argument(
        "--ocr-profile",
        choices=("fast", "adaptive"),
        default="adaptive",
        help="fast=single OCR pass, adaptive=extra passes only when unresolved.",
    )
    args = parser.parse_args()

    manifest, verified, queue = build(
        args.input_dir,
        args.official_registry,
        args.reviewed_overrides,
        progress_every=max(0, args.progress_every),
        sample_size=max(0, args.sample_size),
        sample_seed=args.sample_seed,
        ocr_profile=args.ocr_profile,
    )
    args.manifest.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.verified.write_text(
        json.dumps(verified, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.verification_queue.write_text(
        json.dumps(queue, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest["summary"], ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

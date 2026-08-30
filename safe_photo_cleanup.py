#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verified-photo-preserving cleanup for TCG Grader device-local images.

Safety model:
- Never delete officially verified/manual reference images.
- Never delete images referenced by verified-cert/reference registries.
- Never delete train/validation/holdout/reference/official folders.
- Keep pending/manual-review images.
- Remove only proven duplicates, corrupt/empty images, explicit rejected/quarantine
  images after a grace period, and stale cache/candidate images.
- Default is dry-run. ``run(apply=True)`` performs only the classified safe removals.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPORT_PATH = ROOT / "photo_cleanup_report.json"
MANUAL_REGISTRY = ROOT / "manual_graded_photo_registrations.json"
VERIFIED_CERTS = ROOT / "verified_certifications.json"
VERIFIED_REFS = ROOT / "library_verified_slab_references.json"
LIBRARY_CANDIDATES = ROOT / "library_slab_candidates.json"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
PROTECTED_DIR_TOKENS = {
    "train", "training", "validation", "validate", "holdout", "reference", "references",
    "verified", "official", "gold", "ground_truth", "ground-truth", "calibration",
}
CACHE_DIR_TOKENS = {
    "cache", "cached", "candidate", "candidates", "download", "downloads", "tmp", "temp",
    "scrape", "search_results", "search-results",
}
SCAN_ROOT_NAMES = (
    "GRADE_TRAINING_INBOX",
    "grading_photos",
    "graded_photos",
    "GRADE_PHOTOS",
    "graded_photo_cache",
    "GRADE_PHOTO_CACHE",
    "downloaded_graded_photos",
)
DEFAULT_GRACE_DAYS = 14
DEFAULT_CACHE_DAYS = 7
MAX_HASH_BYTES = 20_000_000


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return default


def _safe_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except (OSError, ValueError):
        return ""


def _is_inside_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
        return True
    except (OSError, ValueError):
        return False


def _parts_lower(path: Path) -> set[str]:
    return {part.lower() for part in path.parts}


def _protected_by_folder(path: Path) -> bool:
    parts = _parts_lower(path)
    return any(token in parts for token in PROTECTED_DIR_TOKENS)


def _cache_by_folder(path: Path) -> bool:
    parts = _parts_lower(path)
    return any(token in parts for token in CACHE_DIR_TOKENS)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    total = 0
    with path.open("rb") as fh:
        while True:
            block = fh.read(1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > MAX_HASH_BYTES:
                raise ValueError("image too large for cleanup hashing")
            h.update(block)
    return h.hexdigest()


def _age_days(path: Path, now_ts: float) -> float:
    try:
        return max(0.0, (now_ts - path.stat().st_mtime) / 86400.0)
    except OSError:
        return 0.0


def _collect_registry_protection() -> tuple[set[str], set[str], dict[str, dict[str, Any]]]:
    protected_paths: set[str] = set()
    protected_hashes: set[str] = set()
    manual_by_path: dict[str, dict[str, Any]] = {}

    manual = _load(MANUAL_REGISTRY, {})
    rows = manual.get("registrations", []) if isinstance(manual, dict) else []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        rel = str(row.get("image_path") or "").strip().replace("\\", "/")
        digest = str(row.get("image_sha256") or "").strip().lower()
        if rel:
            manual_by_path[rel] = row
        official = row.get("official_result") is True or str(row.get("status") or "") == "verified_reference"
        if official:
            if rel:
                protected_paths.add(rel)
            if len(digest) == 64:
                protected_hashes.add(digest)

    for registry_path in (VERIFIED_REFS, LIBRARY_CANDIDATES, VERIFIED_CERTS):
        payload = _load(registry_path, {})
        values = []
        if isinstance(payload, dict):
            for key in ("certifications", "records", "items"):
                if isinstance(payload.get(key), list):
                    values.extend(payload[key])
        for row in values:
            if not isinstance(row, dict):
                continue
            official = (
                row.get("official_result") is True
                or row.get("verified") is True
                or row.get("officially_verified") is True
            )
            if not official:
                continue
            for key in ("image_sha256", "source_sha256", "sha256"):
                digest = str(row.get(key) or "").strip().lower()
                if len(digest) == 64:
                    protected_hashes.add(digest)
            for key in ("image_path", "source_name", "source_asset_name"):
                rel = str(row.get(key) or "").strip().replace("\\", "/")
                if rel and not rel.startswith(("http://", "https://")):
                    protected_paths.add(rel)
    return protected_paths, protected_hashes, manual_by_path


def _scan_roots() -> list[Path]:
    roots = []
    for name in SCAN_ROOT_NAMES:
        path = ROOT / name
        if path.is_dir() and not path.is_symlink():
            roots.append(path)
    # Never scan personal folders outside the program directory automatically.
    return roots


def _candidate_files() -> list[Path]:
    files: list[Path] = []
    seen: set[str] = set()
    for root in _scan_roots():
        for path in root.rglob("*"):
            if not path.is_file() or path.is_symlink() or path.suffix.lower() not in IMAGE_EXTS:
                continue
            try:
                resolved = str(path.resolve())
            except OSError:
                continue
            if resolved in seen or not _is_inside_root(path):
                continue
            seen.add(resolved)
            files.append(path)
    return sorted(files, key=lambda p: p.as_posix())


def _manual_state(rel: str, manual_by_path: dict[str, dict[str, Any]]) -> tuple[str, bool]:
    row = manual_by_path.get(rel)
    if not row:
        return "", False
    status = str(row.get("status") or "")
    verification = str(row.get("verification_state") or "")
    reasons = {str(x) for x in (row.get("quarantine_reasons") or []) if x}
    pending = status == "pending_official_verification" or verification in {
        "queued", "processing", "manual_input_required", "deferred_by_cooldown", "processing_failed"
    }
    hard_rejected = status == "quarantine" and (
        verification == "completed_unverified"
        or any(
            token in reason.lower()
            for reason in reasons
            for token in ("conflict", "mismatch", "invalid", "duplicate")
        )
    )
    return status, bool(hard_rejected and not pending)


def run(*, apply: bool = False, grace_days: int = DEFAULT_GRACE_DAYS,
        cache_days: int = DEFAULT_CACHE_DAYS) -> dict[str, Any]:
    grace_days = max(1, min(365, int(grace_days)))
    cache_days = max(1, min(365, int(cache_days)))
    protected_paths, protected_hashes, manual_by_path = _collect_registry_protection()
    now_ts = datetime.now(timezone.utc).timestamp()
    files = _candidate_files()
    seen_hash: dict[str, str] = {}
    rows: list[dict[str, Any]] = []
    removed = 0
    freed = 0
    protected_count = 0
    review_count = 0

    for path in files:
        rel = _safe_rel(path)
        if not rel:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        age = _age_days(path, now_ts)
        reason = "keep_review"
        action = "keep"
        digest = ""
        status, hard_rejected = _manual_state(rel, manual_by_path)

        if rel in protected_paths or _protected_by_folder(path):
            reason = "verified_or_dataset_protected"
            protected_count += 1
        else:
            try:
                digest = _sha256(path) if size > 0 else ""
            except (OSError, ValueError):
                digest = ""
            if digest and digest in protected_hashes:
                reason = "verified_hash_protected"
                protected_count += 1
            elif size == 0:
                reason = "empty_image"
                action = "delete"
            elif digest and digest in seen_hash:
                reason = f"duplicate_of:{seen_hash[digest]}"
                action = "delete"
            elif hard_rejected and age >= grace_days:
                reason = f"explicit_quarantine_older_than_{grace_days}d"
                action = "delete"
            elif _cache_by_folder(path) and age >= cache_days and not status:
                reason = f"stale_unreferenced_cache_older_than_{cache_days}d"
                action = "delete"
            else:
                reason = "pending_or_unclassified_keep"
                review_count += 1

        if digest and action == "keep":
            seen_hash.setdefault(digest, rel)
        if action == "delete" and apply:
            try:
                path.unlink()
                removed += 1
                freed += size
            except OSError:
                action = "delete_failed"
        rows.append({
            "path": rel, "bytes": size, "age_days": round(age, 2),
            "action": action, "reason": reason,
        })

    report = {
        "version": 1,
        "updated_at": _now(),
        "mode": "apply" if apply else "dry_run",
        "policy": {
            "verified_reference_never_deleted": True,
            "verified_hash_never_deleted": True,
            "train_validation_holdout_never_deleted": True,
            "pending_manual_review_never_deleted": True,
            "external_personal_folders_scanned": False,
            "grace_days": grace_days,
            "cache_days": cache_days,
        },
        "summary": {
            "scanned_images": len(rows),
            "protected_images": protected_count,
            "review_keep_images": review_count,
            "delete_candidates": sum(row["action"] == "delete" for row in rows),
            "deleted_images": removed,
            "freed_bytes": freed,
        },
        "items": rows[-2000:],
    }
    try:
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    except OSError:
        pass
    return report


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TCG 학습사진 안전 정리")
    parser.add_argument("--apply", action="store_true", help="안전 판정된 사진만 실제 삭제")
    parser.add_argument("--grace-days", type=int, default=DEFAULT_GRACE_DAYS)
    parser.add_argument("--cache-days", type=int, default=DEFAULT_CACHE_DAYS)
    args = parser.parse_args()
    result = run(apply=args.apply, grace_days=args.grace_days, cache_days=args.cache_days)
    print(json.dumps(result["summary"], ensure_ascii=False))

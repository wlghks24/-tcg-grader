#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fail-closed, verified-photo-preserving cleanup for TCG Grader device-local images.

Safety model:
- Never delete officially verified/manual reference images.
- Never delete images referenced by verified-cert/reference registries.
- Never delete train/validation/holdout/reference/official folders.
- Keep pending/manual-review images, including duplicate pending uploads.
- Respect quarantine grace periods before any generic duplicate/cache cleanup.
- If an existing protection registry is unreadable/invalid, disable destructive cleanup.
- Default is dry-run. ``run(apply=True)`` performs only classified safe removals.
"""

from __future__ import annotations

import hashlib
import json
import re
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
    "verified", "official", "gold", "groundtruth", "calibration",
}
CACHE_DIR_TOKENS = {
    "cache", "cached", "candidate", "candidates", "download", "downloads", "downloaded",
    "tmp", "temp", "scrape", "searchresults",
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


def _load_checked(path: Path) -> tuple[dict[str, Any], str | None]:
    """Return parsed dict and an error string. Missing registries are not errors."""
    try:
        if not path.exists():
            return {}, None
        if path.is_symlink() or not path.is_file():
            return {}, f"{path.name}:unsafe_path"
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw)
        if not isinstance(value, dict):
            return {}, f"{path.name}:root_not_object"
        return value, None
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        return {}, f"{path.name}:{type(exc).__name__}"


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


def _relative_folder_parts(path: Path) -> tuple[str, ...]:
    """Return directory parts below the configured scan root, excluding the filename."""
    try:
        rel = path.resolve().relative_to(ROOT.resolve())
    except (OSError, ValueError):
        return ()
    parts = list(rel.parts[:-1])
    if parts and parts[0].lower() in {name.lower() for name in SCAN_ROOT_NAMES}:
        parts = parts[1:]
    return tuple(parts)


def _tokens_from_parts(parts: tuple[str, ...]) -> set[str]:
    tokens: set[str] = set()
    for part in parts:
        lower = part.lower()
        compact = re.sub(r"[^a-z0-9]+", "", lower)
        if compact:
            tokens.add(compact)
        tokens.update(x for x in re.split(r"[^a-z0-9]+", lower) if x)
    return tokens


def _protected_by_folder(path: Path) -> bool:
    return bool(_tokens_from_parts(_relative_folder_parts(path)) & PROTECTED_DIR_TOKENS)


def _cache_by_folder(path: Path) -> bool:
    try:
        rel = path.resolve().relative_to(ROOT.resolve())
        root_name = rel.parts[0].lower() if rel.parts else ""
    except (OSError, ValueError):
        return False
    cache_roots = {
        "graded_photo_cache", "grade_photo_cache", "downloaded_graded_photos",
    }
    if root_name in cache_roots:
        return True
    return bool(_tokens_from_parts(_relative_folder_parts(path)) & CACHE_DIR_TOKENS)


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


def _normalize_registry_path(value: Any) -> str:
    text = str(value or "").strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


def _collect_registry_protection() -> tuple[
    set[str], set[str], dict[str, dict[str, Any]], list[str]
]:
    protected_paths: set[str] = set()
    protected_hashes: set[str] = set()
    manual_by_path: dict[str, dict[str, Any]] = {}
    registry_errors: list[str] = []

    manual, error = _load_checked(MANUAL_REGISTRY)
    if error:
        registry_errors.append(error)
    rows = manual.get("registrations", []) if isinstance(manual, dict) else []
    if rows is not None and not isinstance(rows, list):
        registry_errors.append(f"{MANUAL_REGISTRY.name}:registrations_not_list")
        rows = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        rel = _normalize_registry_path(row.get("image_path"))
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
        payload, error = _load_checked(registry_path)
        if error:
            registry_errors.append(error)
            continue
        values: list[Any] = []
        for key in ("certifications", "records", "items"):
            current = payload.get(key)
            if current is None:
                continue
            if not isinstance(current, list):
                registry_errors.append(f"{registry_path.name}:{key}_not_list")
                continue
            values.extend(current)
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
                rel = _normalize_registry_path(row.get(key))
                if rel and not rel.startswith(("http://", "https://")):
                    protected_paths.add(rel)

    return protected_paths, protected_hashes, manual_by_path, sorted(set(registry_errors))


def _scan_roots() -> list[Path]:
    roots = []
    for name in SCAN_ROOT_NAMES:
        path = ROOT / name
        if path.is_dir() and not path.is_symlink():
            roots.append(path)
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


def _manual_state(rel: str, manual_by_path: dict[str, dict[str, Any]]) -> tuple[str, bool, bool]:
    row = manual_by_path.get(rel)
    if not row:
        return "", False, False
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
    registered = bool(status or verification or row)
    return status, bool(hard_rejected and not pending), registered


def run(*, apply: bool = False, grace_days: int = DEFAULT_GRACE_DAYS,
        cache_days: int = DEFAULT_CACHE_DAYS) -> dict[str, Any]:
    grace_days = max(1, min(365, int(grace_days)))
    cache_days = max(1, min(365, int(cache_days)))
    protected_paths, protected_hashes, manual_by_path, registry_errors = _collect_registry_protection()
    destructive_allowed = not registry_errors
    now_ts = datetime.now(timezone.utc).timestamp()
    files = _candidate_files()
    seen_hash: dict[str, str] = {}
    rows: list[dict[str, Any]] = []
    removed = 0
    freed = 0
    protected_count = 0
    review_count = 0
    guarded_count = 0

    for path in files:
        rel = _safe_rel(path)
        if not rel:
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        age = _age_days(path, now_ts)
        decision = "keep"
        action = "keep"
        reason = "pending_or_unclassified_keep"
        digest = ""
        status, hard_rejected, registered = _manual_state(rel, manual_by_path)

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
            elif registered:
                if hard_rejected and age >= grace_days:
                    decision = "delete"
                    reason = f"explicit_quarantine_older_than_{grace_days}d"
                else:
                    reason = "manual_registry_pending_or_grace_protected"
                    protected_count += 1
            elif size == 0:
                decision = "delete"
                reason = "empty_unreferenced_image"
            elif digest and digest in seen_hash:
                decision = "delete"
                reason = f"duplicate_of:{seen_hash[digest]}"
            elif _cache_by_folder(path) and age >= cache_days:
                decision = "delete"
                reason = f"stale_unreferenced_cache_older_than_{cache_days}d"
            else:
                review_count += 1

        if digest and decision == "keep":
            seen_hash.setdefault(digest, rel)

        if decision == "delete":
            if apply and not destructive_allowed:
                action = "guarded_keep"
                guarded_count += 1
            elif apply:
                try:
                    path.unlink()
                    action = "deleted"
                    removed += 1
                    freed += size
                except OSError:
                    action = "delete_failed"
            else:
                action = "delete_candidate"

        rows.append({
            "path": rel,
            "bytes": size,
            "age_days": round(age, 2),
            "decision": decision,
            "action": action,
            "reason": reason,
        })

    mode = "dry_run"
    if apply and destructive_allowed:
        mode = "apply"
    elif apply and not destructive_allowed:
        mode = "apply_guarded_no_delete"

    report = {
        "version": 2,
        "updated_at": _now(),
        "mode": mode,
        "registry_guard": {
            "destructive_allowed": destructive_allowed,
            "errors": registry_errors,
        },
        "policy": {
            "verified_reference_never_deleted": True,
            "verified_hash_never_deleted": True,
            "train_validation_holdout_never_deleted": True,
            "pending_manual_review_never_deleted": True,
            "manual_registry_outranks_duplicate_cleanup": True,
            "registry_parse_failure_disables_delete": True,
            "external_personal_folders_scanned": False,
            "grace_days": grace_days,
            "cache_days": cache_days,
        },
        "summary": {
            "scanned_images": len(rows),
            "protected_images": protected_count,
            "review_keep_images": review_count,
            "delete_candidates": sum(row["decision"] == "delete" for row in rows),
            "guarded_keep_images": guarded_count,
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

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fail-closed photo cleanup for TCG Grader.

v133 safety policy:
- User/manual uploads and training/reference/validation/holdout folders are never auto-deleted.
- Every local photo reference found in protection/candidate registries is protected,
  even when the candidate is still unverified or quarantined.
- Automatic deletion is restricted to explicitly disposable cache/download folders.
- Cache files must be old enough before deletion; fresh duplicates are kept.
- Hash/read failures keep the photo.
- If an existing protection registry is unreadable or structurally invalid, destructive
  cleanup is disabled for that run.
- Dry-run is the default.
"""

from __future__ import annotations

import hashlib
import json
import os
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
GRADED_PHOTO_CANDIDATES = ROOT / "graded_photo_candidates.json"
EBAY_CANDIDATES = ROOT / "ebay_grader_candidates.json"

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
PROTECTED_DIR_TOKENS = {
    "train", "training", "validation", "validate", "holdout", "reference", "references",
    "verified", "official", "gold", "groundtruth", "calibration", "manual",
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
DISPOSABLE_ROOT_NAMES = {
    "graded_photo_cache", "grade_photo_cache", "downloaded_graded_photos",
}
CRITICAL_REGISTRIES = (
    (VERIFIED_REFS, ("certifications", "records", "items")),
    (LIBRARY_CANDIDATES, ("records", "certifications", "items")),
    (VERIFIED_CERTS, ("certifications", "records", "items")),
    (GRADED_PHOTO_CANDIDATES, ("records", "items", "certifications")),
    (EBAY_CANDIDATES, ("items", "records", "certifications")),
)
DEFAULT_GRACE_DAYS = 14
DEFAULT_CACHE_DAYS = 14
MAX_HASH_BYTES = 64_000_000
MAX_REGISTRY_BYTES = 32_000_000

_HASH_KEYS = ("image_sha256", "source_sha256", "sha256")
_PATH_KEYS = (
    "image_path", "source_path", "source_name", "source_asset_name",
    "local_path", "cached_path", "download_path",
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_checked(path: Path) -> tuple[dict[str, Any], str | None]:
    """Return parsed dict and an error string. Missing registries are not errors."""
    try:
        if not path.exists():
            return {}, None
        if path.is_symlink() or not path.is_file():
            return {}, f"{path.name}:unsafe_path"
        size = path.stat().st_size
        if size > MAX_REGISTRY_BYTES:
            return {}, f"{path.name}:too_large"
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


def _relative_parts(path: Path) -> tuple[str, ...]:
    try:
        return path.resolve().relative_to(ROOT.resolve()).parts
    except (OSError, ValueError):
        return ()


def _relative_folder_parts(path: Path) -> tuple[str, ...]:
    parts = list(_relative_parts(path)[:-1])
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


def _protected_by_location(path: Path) -> bool:
    parts = _relative_parts(path)
    if not parts:
        return True
    root_name = parts[0].lower()
    # The training inbox is user/evidence storage, never disposable cache.
    if root_name == "grade_training_inbox":
        return True
    return bool(_tokens_from_parts(_relative_folder_parts(path)) & PROTECTED_DIR_TOKENS)


def _disposable_by_location(path: Path) -> bool:
    parts = _relative_parts(path)
    if not parts:
        return False
    root_name = parts[0].lower()
    if root_name in DISPOSABLE_ROOT_NAMES:
        return True
    # Generic photo roots are not disposable unless the user/code explicitly placed
    # the image under a cache/candidate/download/tmp subfolder.
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


def _add_reference(
    row: dict[str, Any],
    protected_paths: set[str],
    protected_names: set[str],
    protected_hashes: set[str],
) -> None:
    for key in _HASH_KEYS:
        digest = str(row.get(key) or "").strip().lower()
        if re.fullmatch(r"[0-9a-f]{64}", digest):
            protected_hashes.add(digest)
    for key in _PATH_KEYS:
        rel = _normalize_registry_path(row.get(key))
        if not rel or rel.startswith(("http://", "https://", "data:")):
            continue
        # A basename-only source_name cannot be matched as a full relative path;
        # protect the basename conservatively instead.
        if "/" in rel:
            protected_paths.add(rel)
            protected_names.add(Path(rel).name)
        else:
            protected_names.add(rel)


def _rows_from_registry(
    path: Path,
    payload: dict[str, Any],
    keys: tuple[str, ...],
    *,
    require_one_key_when_present: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    values: list[dict[str, Any]] = []
    present_keys = [key for key in keys if key in payload]
    if path.exists() and require_one_key_when_present and not present_keys:
        return [], [f"{path.name}:expected_list_key_missing"]
    for key in present_keys:
        current = payload.get(key)
        if not isinstance(current, list):
            errors.append(f"{path.name}:{key}_not_list")
            continue
        for index, row in enumerate(current):
            if not isinstance(row, dict):
                errors.append(f"{path.name}:{key}[{index}]_not_object")
                continue
            values.append(row)
    return values, errors


def _collect_registry_protection() -> tuple[
    set[str], set[str], set[str], dict[str, dict[str, Any]], list[str]
]:
    protected_paths: set[str] = set()
    protected_names: set[str] = set()
    protected_hashes: set[str] = set()
    manual_by_path: dict[str, dict[str, Any]] = {}
    registry_errors: list[str] = []

    manual, error = _load_checked(MANUAL_REGISTRY)
    if error:
        registry_errors.append(error)
    if MANUAL_REGISTRY.exists():
        if "registrations" not in manual:
            registry_errors.append(f"{MANUAL_REGISTRY.name}:registrations_key_missing")
            manual_rows: list[dict[str, Any]] = []
        else:
            manual_rows, row_errors = _rows_from_registry(
                MANUAL_REGISTRY, manual, ("registrations",), require_one_key_when_present=True
            )
            registry_errors.extend(row_errors)
    else:
        manual_rows = []

    for row in manual_rows:
        rel = _normalize_registry_path(row.get("image_path"))
        if rel:
            manual_by_path[rel] = row
        # Every manual registration is user evidence, not only officially verified rows.
        _add_reference(row, protected_paths, protected_names, protected_hashes)

    for registry_path, keys in CRITICAL_REGISTRIES:
        payload, error = _load_checked(registry_path)
        if error:
            registry_errors.append(error)
            continue
        if not registry_path.exists():
            continue
        values, row_errors = _rows_from_registry(registry_path, payload, keys)
        registry_errors.extend(row_errors)
        # Any locally referenced candidate remains protected until its registry entry
        # is intentionally pruned. Verification status does not matter for cleanup.
        for row in values:
            _add_reference(row, protected_paths, protected_names, protected_hashes)

    return (
        protected_paths,
        protected_names,
        protected_hashes,
        manual_by_path,
        sorted(set(registry_errors)),
    )


def _scan_roots() -> list[Path]:
    roots = []
    for name in SCAN_ROOT_NAMES:
        path = ROOT / name
        if path.is_dir() and not path.is_symlink():
            roots.append(path)
    return roots


def _candidate_files() -> list[Path]:
    """Walk known roots without ever following directory symlinks."""
    files: list[Path] = []
    seen: set[str] = set()
    for root in _scan_roots():
        for current, dirs, names in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            # Explicitly prune symlink directories even on Python versions where
            # pathlib/os traversal behavior differs.
            dirs[:] = [
                name for name in dirs
                if not (current_path / name).is_symlink()
            ]
            for name in names:
                path = current_path / name
                if path.is_symlink() or path.suffix.lower() not in IMAGE_EXTS:
                    continue
                try:
                    if not path.is_file():
                        continue
                    resolved = str(path.resolve())
                except OSError:
                    continue
                if resolved in seen or not _is_inside_root(path):
                    continue
                seen.add(resolved)
                files.append(path)
    return sorted(files, key=lambda p: p.as_posix())


def run(*, apply: bool = False, grace_days: int = DEFAULT_GRACE_DAYS,
        cache_days: int = DEFAULT_CACHE_DAYS) -> dict[str, Any]:
    # grace_days remains in the report/API for backward compatibility. v133 no longer
    # auto-deletes manually registered rejected photos at any age.
    grace_days = max(1, min(365, int(grace_days)))
    cache_days = max(1, min(365, int(cache_days)))
    (
        protected_paths,
        protected_names,
        protected_hashes,
        manual_by_path,
        registry_errors,
    ) = _collect_registry_protection()
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
    hash_guarded_count = 0

    for path in files:
        rel = _safe_rel(path)
        if not rel:
            continue
        try:
            metadata = os.stat(path, follow_symlinks=False)
            size = metadata.st_size
            signature = (
                metadata.st_dev, metadata.st_ino, metadata.st_mtime_ns, metadata.st_size
            )
        except OSError:
            continue
        age = _age_days(path, now_ts)
        decision = "keep"
        action = "keep"
        reason = "non_disposable_photo_root_keep"
        digest = ""
        hash_error = False

        if (
            rel in protected_paths
            or path.name in protected_names
            or rel in manual_by_path
            or _protected_by_location(path)
        ):
            reason = "registry_or_dataset_protected"
            protected_count += 1
        else:
            if size > 0:
                try:
                    digest = _sha256(path)
                except (OSError, ValueError):
                    hash_error = True
            if hash_error:
                reason = "hash_unavailable_keep"
                hash_guarded_count += 1
                review_count += 1
            elif digest and digest in protected_hashes:
                reason = "registry_hash_protected"
                protected_count += 1
            elif not _disposable_by_location(path):
                # Do not auto-clean generic grading/training photo roots.
                reason = "non_disposable_photo_root_keep"
                review_count += 1
            elif age < cache_days:
                reason = f"fresh_disposable_cache_younger_than_{cache_days}d"
                review_count += 1
            else:
                decision = "delete"
                if size == 0:
                    reason = f"stale_empty_cache_older_than_{cache_days}d"
                elif digest and digest in seen_hash:
                    reason = f"stale_duplicate_cache_of:{seen_hash[digest]}"
                else:
                    reason = f"stale_unreferenced_cache_older_than_{cache_days}d"

        if digest and decision == "keep":
            seen_hash.setdefault(digest, rel)

        if decision == "delete":
            if apply and not destructive_allowed:
                action = "guarded_keep"
                guarded_count += 1
            elif apply:
                try:
                    # Revalidate immediately before unlink so a collector cannot replace
                    # or update a stale cache file between classification and deletion.
                    current = os.stat(path, follow_symlinks=False)
                    current_signature = (
                        current.st_dev, current.st_ino, current.st_mtime_ns, current.st_size
                    )
                    if (
                        path.is_symlink()
                        or current_signature != signature
                        or not _is_inside_root(path)
                        or not _disposable_by_location(path)
                    ):
                        action = "guarded_keep"
                        reason = "changed_or_unsafe_before_delete_keep"
                        guarded_count += 1
                    else:
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
        "version": 3,
        "updated_at": _now(),
        "mode": mode,
        "registry_guard": {
            "destructive_allowed": destructive_allowed,
            "errors": registry_errors,
        },
        "policy": {
            "manual_and_training_photos_never_auto_deleted": True,
            "all_registry_local_references_protected": True,
            "verified_reference_never_deleted": True,
            "verified_hash_never_deleted": True,
            "generic_photo_roots_are_non_disposable": True,
            "destructive_cleanup_restricted_to_cache_locations": True,
            "fresh_cache_never_deleted": True,
            "hash_failure_keeps_photo": True,
            "symlink_directories_never_traversed": True,
            "file_change_before_delete_keeps_photo": True,
            "registry_parse_failure_disables_delete": True,
            "external_personal_folders_scanned": False,
            "grace_days_legacy": grace_days,
            "cache_days": cache_days,
        },
        "summary": {
            "scanned_images": len(rows),
            "protected_images": protected_count,
            "review_keep_images": review_count,
            "hash_guarded_images": hash_guarded_count,
            "delete_candidates": sum(row["decision"] == "delete" for row in rows),
            "guarded_keep_images": guarded_count,
            "deleted_images": removed,
            "freed_bytes": freed,
        },
        "items": rows[-2000:],
    }
    try:
        if not REPORT_PATH.is_symlink():
            encoded = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
            tmp = REPORT_PATH.with_name(REPORT_PATH.name + ".tmp")
            tmp.write_text(encoded, encoding="utf-8")
            tmp.replace(REPORT_PATH)
    except OSError:
        pass
    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="TCG 학습사진 안전 정리")
    parser.add_argument("--apply", action="store_true", help="안전 판정된 오래된 캐시만 실제 삭제")
    parser.add_argument("--grace-days", type=int, default=DEFAULT_GRACE_DAYS)
    parser.add_argument("--cache-days", type=int, default=DEFAULT_CACHE_DAYS)
    args = parser.parse_args()
    result = run(apply=args.apply, grace_days=args.grace_days, cache_days=args.cache_days)
    print(json.dumps(result["summary"], ensure_ascii=False))

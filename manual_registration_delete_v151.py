#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Safe user-requested cancellation for unverified manual slab registrations.

This removes a mistaken manual registration and its locally stored front/back
and manual-official-proof images. A live officially verified registration is
never deletable through this helper.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

import manual_graded_photo_registration as manual_photo
from safe_runtime import atomic_write_json

ROOT = Path(__file__).resolve().parent
PROOF_ROOT = ROOT / "GRADE_TRAINING_INBOX" / "manual_official_proof"
REFERENCE_PATH = ROOT / "manual_official_proof_references.json"


def _safe_unlink(relative_path: Any) -> bool:
    """Unlink a regular file through no-follow directory descriptors.

    Never resolve a stored alias to a different image. If this platform cannot
    enforce O_NOFOLLOW/dir_fd, preserve the file rather than guessing.
    """
    text = str(relative_path or "").strip()
    if not text or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        return False
    directory_fd = None
    try:
        relative = Path(text)
        parts = relative.parts
        if relative.is_absolute() or any(part in {".", ".."} for part in parts):
            return False
        allowed = (manual_photo.INBOX_ROOT.relative_to(ROOT).parts, PROOF_ROOT.relative_to(ROOT).parts)
        if not any(len(parts) > len(prefix) and parts[:len(prefix)] == prefix for prefix in allowed):
            return False
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        directory_fd = os.open(ROOT, flags)
        for component in parts[:-1]:
            child_fd = os.open(component, flags, dir_fd=directory_fd)
            os.close(directory_fd)
            directory_fd = child_fd
        if not stat.S_ISREG(os.stat(parts[-1], dir_fd=directory_fd, follow_symlinks=False).st_mode):
            return False
        os.unlink(parts[-1], dir_fd=directory_fd)
        return True
    except (OSError, ValueError, RuntimeError, TypeError):
        return False
    finally:
        if directory_fd is not None:
            os.close(directory_fd)


def _remove_reference_entries(registration_id: str) -> int:
    try:
        if REFERENCE_PATH.is_symlink() or not REFERENCE_PATH.is_file():
            return 0
        import json
        payload = json.loads(REFERENCE_PATH.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return 0
        values = payload.get("references", [])
        if not isinstance(values, list):
            return 0
        kept = [item for item in values if not (isinstance(item, dict) and str(item.get("registration_id") or "") == registration_id)]
        removed = len(values) - len(kept)
        if removed:
            payload["references"] = kept
            payload["updated_at"] = manual_photo._now()
            atomic_write_json(REFERENCE_PATH, payload, suffix=".manual-delete-reference.tmp")
        return removed
    except (OSError, UnicodeError, ValueError, TypeError):
        return 0


def delete_registration(registration_id: str) -> dict[str, Any]:
    registration_id = str(registration_id or "").strip()[:80]
    if not registration_id:
        raise ValueError("삭제할 수동등록 번호가 없습니다.")

    with manual_photo.LOCK:
        registry = manual_photo._registry()
        index, row = manual_photo._find_row(registry, registration_id)
        row = dict(row)
        if row.get("official_result") is True:
            raise ValueError("공식검증 완료 자료는 이 화면에서 삭제할 수 없습니다.")

        registrations = registry.get("registrations", [])
        image_fields = ("image_path", "back_image_path", "manual_official_proof_path",
                        "front_oblique_image_path", "back_oblique_image_path")
        shared_paths = {
            str(other.get(field) or "")
            for pos, other in enumerate(registrations)
            if pos != index and isinstance(other, dict)
            for field in image_fields
            if other.get(field)
        }
        # Resolve ONLY to compare ownership, never as the unlink destination.
        # This also protects a verified row that uses a different path alias.
        shared_targets = {(ROOT / path).resolve() for path in shared_paths}
        paths = [
            path for field in ("image_path", "back_image_path", "manual_official_proof_path")
            if isinstance((path := row.get(field)), str)
            and Path(path).name.startswith((registration_id + ".", registration_id + "_", registration_id + "-"))
            and (ROOT / path).resolve() not in shared_targets
        ]
        registry["registrations"] = [
            item for pos, item in enumerate(registrations)
            if pos != index
        ]
        manual_photo._save_registry(registry)
        # Keep the registry lock through file/reference cleanup so another
        # registration cannot claim the same path between save and unlink.
        files_deleted = sum(1 for path in paths if _safe_unlink(path))
        references_deleted = _remove_reference_entries(registration_id)
    return {
        "ok": True,
        "accepted": True,
        "deleted": True,
        "registration_id": registration_id,
        "files_deleted": files_deleted,
        "references_deleted": references_deleted,
        "official_result_deleted": False,
        "raw_grade_calibration_changed": False,
    }

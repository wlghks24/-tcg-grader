#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Safe user-requested cancellation for unverified manual slab registrations.

This removes a mistaken manual registration and its locally stored front/back
and manual-official-proof images. A live officially verified registration is
never deletable through this helper.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import manual_graded_photo_registration as manual_photo
from safe_runtime import atomic_write_json

ROOT = Path(__file__).resolve().parent
PROOF_ROOT = ROOT / "GRADE_TRAINING_INBOX" / "manual_official_proof"
REFERENCE_PATH = ROOT / "manual_official_proof_references.json"


def _safe_unlink(relative_path: Any) -> bool:
    text = str(relative_path or "").strip()
    if not text:
        return False
    try:
        candidate = (ROOT / text).resolve()
        allowed_roots = (manual_photo.INBOX_ROOT.resolve(), PROOF_ROOT.resolve())
        if not any(candidate != root and root in candidate.parents for root in allowed_roots):
            return False
        if candidate.is_symlink() or not candidate.is_file():
            return False
        candidate.unlink(missing_ok=True)
        return True
    except (OSError, ValueError, RuntimeError):
        return False


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

        paths = [
            row.get("image_path"),
            row.get("back_image_path"),
            row.get("manual_official_proof_path"),
        ]
        registrations = registry.get("registrations", [])
        registry["registrations"] = [
            item for pos, item in enumerate(registrations)
            if pos != index
        ]
        manual_photo._save_registry(registry)

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

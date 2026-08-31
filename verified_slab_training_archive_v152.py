#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Archive verified front/back graded-card photos by grading company.

The archive is intentionally reference-learning only. Slab labels must never be
used to train RAW-card grade calibration because the slab itself contains the
answer. Only rows with a complete company/certificate/grade identity, both
front and back photos, and either live official verification or a matched manual
official-page reference are copied.

On Android/Termux the preferred archive is:
  /storage/emulated/0/Download/TCG등급학습/검증완료/<COMPANY>/<GAME>/...
A .nomedia marker is written at the archive root so these managed copies do not
clutter Photos/Gallery. The original user-selected photo is never deleted.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import shutil
import time
from typing import Any, Iterable

import manual_graded_photo_registration as manual_photo
from safe_runtime import atomic_write_bytes, atomic_write_json, atomic_write_text, safe_read_bytes

PATCH_ID = 152
ROOT = Path(__file__).resolve().parent
INTERNAL_MANIFEST = ROOT / "verified_slab_training_archive.json"
ANDROID_DOWNLOAD = Path("/storage/emulated/0/Download")
FALLBACK_ARCHIVE = ROOT / "GRADE_TRAINING_INBOX" / "verified_archive"
COMPANIES = ("PSA", "BGS", "CGC", "TAG", "BRG")
GAMES = ("pokemon", "onepiece", "naruto")
MAX_COPY_BYTES = 8_000_000


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _grade(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or not 1 <= number <= 10:
        return None
    return number


def _cert(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()[:24]


def _grade_text(value: float) -> str:
    return str(int(value)) if abs(value - round(value)) < 1e-9 else f"{value:.1f}"


def archive_root() -> Path:
    override = str(os.environ.get("TCG_VERIFIED_ARCHIVE_ROOT") or "").strip()
    if override:
        return Path(override).expanduser()
    try:
        if ANDROID_DOWNLOAD.is_dir() and os.access(ANDROID_DOWNLOAD, os.R_OK | os.W_OK):
            return ANDROID_DOWNLOAD / "TCG등급학습" / "검증완료"
    except OSError:
        pass
    return FALLBACK_ARCHIVE


def _verification_kind(row: dict[str, Any]) -> str | None:
    if row.get("official_result") is True:
        return "live_official_verified"
    proof_matched = (
        row.get("manual_official_proof_registered") is True
        and (
            str(row.get("manual_official_proof_state") or "") == "matched"
            or str(row.get("verification_state") or "") == "manual_official_proof_matched"
        )
    )
    if proof_matched:
        return "manual_official_reference"
    return None


def _identity(row: dict[str, Any]) -> tuple[str, str, float, str] | None:
    company = str(row.get("company") or row.get("ocr_company") or "").upper().strip()
    game = str(row.get("game") or "").lower().strip()
    cert = _cert(row.get("certification_id") or row.get("ocr_certification_id"))
    grade = _grade(row.get("claimed_grade") if row.get("claimed_grade") is not None else row.get("ocr_grade"))
    if company not in COMPANIES or game not in GAMES or len(cert) < 6 or grade is None:
        return None
    return company, cert, grade, game


def _eligible(row: dict[str, Any]) -> bool:
    return bool(
        _verification_kind(row)
        and _identity(row)
        and str(row.get("image_path") or "").strip()
        and str(row.get("back_image_path") or "").strip()
    )


def _allowed_source(relative_path: Any, source_root: Path) -> Path | None:
    text = str(relative_path or "").strip()
    if not text:
        return None
    try:
        source_root = source_root.resolve()
        candidate = (source_root / text).resolve()
        allowed = (
            (source_root / "GRADE_TRAINING_INBOX" / "manual").resolve(),
            (source_root / "GRADE_TRAINING_INBOX" / "manual_official_proof").resolve(),
        )
        if not any(candidate != root and root in candidate.parents for root in allowed):
            return None
        if candidate.is_symlink() or not candidate.is_file():
            return None
        size = candidate.stat().st_size
        if size <= 0 or size > MAX_COPY_BYTES:
            return None
        return candidate
    except (OSError, ValueError, RuntimeError):
        return None


def _safe_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink() or target.parent.is_symlink():
        raise ValueError("archive_symlink_blocked")
    data = safe_read_bytes(source, max_bytes=MAX_COPY_BYTES)
    atomic_write_bytes(target, data, suffix=".verified-archive.tmp")


def _pair_folder(row: dict[str, Any], target_root: Path) -> Path:
    identity = _identity(row)
    if identity is None:
        raise ValueError("verified archive identity incomplete")
    company, cert, grade, game = identity
    registration_id = re.sub(r"[^A-Za-z0-9._-]", "_", str(row.get("registration_id") or "unknown"))[:80]
    name = f"{company}_{_grade_text(grade)}_{cert}_{registration_id}"
    return target_root / company / game / name


def _entry_from_row(row: dict[str, Any], target_root: Path, source_root: Path) -> dict[str, Any] | None:
    if not _eligible(row):
        return None
    identity = _identity(row)
    kind = _verification_kind(row)
    assert identity is not None and kind is not None
    company, cert, grade, game = identity
    front = _allowed_source(row.get("image_path"), source_root)
    back = _allowed_source(row.get("back_image_path"), source_root)
    if front is None or back is None:
        return None

    folder = _pair_folder(row, target_root)
    folder.mkdir(parents=True, exist_ok=True)
    front_target = folder / ("front" + (front.suffix.lower() if front.suffix.lower() in {".jpg", ".jpeg", ".png"} else ".jpg"))
    back_target = folder / ("back" + (back.suffix.lower() if back.suffix.lower() in {".jpg", ".jpeg", ".png"} else ".jpg"))
    _safe_copy(front, front_target)
    _safe_copy(back, back_target)

    proof_target: Path | None = None
    proof = _allowed_source(row.get("manual_official_proof_path"), source_root)
    if proof is not None:
        proof_target = folder / ("official_proof" + (proof.suffix.lower() if proof.suffix.lower() in {".jpg", ".jpeg", ".png"} else ".jpg"))
        _safe_copy(proof, proof_target)

    rel = lambda p: p.relative_to(target_root).as_posix()
    entry = {
        "registration_id": row.get("registration_id"),
        "company": company,
        "game": game,
        "grade": grade,
        "certification_id": cert,
        "card_name": row.get("card_name"),
        "card_number": row.get("card_number"),
        "verification_kind": kind,
        "official_result": row.get("official_result") is True,
        "manual_official_reference": kind == "manual_official_reference",
        "front_back_pair_complete": True,
        "front_sha256": row.get("image_sha256"),
        "back_sha256": row.get("back_image_sha256"),
        "front_path": rel(front_target),
        "back_path": rel(back_target),
        "proof_path": rel(proof_target) if proof_target else None,
        "learning_eligibility": (
            "reference_learning_only" if kind == "live_official_verified"
            else "reference_only_pending_live_official_verification"
        ),
        "training_role": "slab_reference_only",
        "raw_grade_calibration_eligible": False,
        "source_registration_updated_at": row.get("updated_at"),
        "archived_at": _now(),
    }
    atomic_write_json(folder / "학습정보.json", entry, suffix=".verified-meta.tmp")
    return entry


def _remove_pair_folder(entry: dict[str, Any], target_root: Path) -> bool:
    try:
        front = target_root / str(entry.get("front_path") or "")
        folder = front.parent.resolve()
        root = target_root.resolve()
        if folder == root or root not in folder.parents or folder.is_symlink():
            return False
        if folder.is_dir():
            shutil.rmtree(folder)
            return True
    except (OSError, ValueError, RuntimeError):
        return False
    return False


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        if path.is_symlink() or not path.is_file():
            return {"entries": []}
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"entries": []}
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return {"entries": []}


def _write_readme(target_root: Path) -> None:
    text = (
        "TCG 검증완료 등급사진 학습 보관함\n"
        "- PSA/BGS/CGC/TAG/BRG 업체별 → pokemon/onepiece/naruto 게임별로 정리됩니다.\n"
        "- 인증번호 + 등급 + 앞면 + 뒷면이 모두 있는 검증완료 자료만 들어옵니다.\n"
        "- .nomedia 파일 때문에 이 보관함의 관리용 복사본은 Photos/Gallery에 표시하지 않습니다.\n"
        "- 슬랩 사진은 참고학습 전용입니다. RAW 카드 등급 보정학습에는 사용하지 않습니다.\n"
        "- live_official_verified와 manual_official_reference는 학습목록에서 구분됩니다.\n"
    )
    atomic_write_text(target_root / "README_검증완료.txt", text, suffix=".archive-readme.tmp")


def sync_rows(rows: Iterable[dict[str, Any]], *, target_root: Path, source_root: Path = ROOT, prune: bool = True) -> dict[str, Any]:
    target_root = target_root.expanduser()
    target_root.mkdir(parents=True, exist_ok=True)
    atomic_write_text(target_root / ".nomedia", "", suffix=".nomedia.tmp")
    _write_readme(target_root)

    external_manifest_path = target_root / "검증완료_학습목록.json"
    previous = _load_manifest(external_manifest_path)
    previous_entries = [dict(item) for item in previous.get("entries", []) if isinstance(item, dict)]
    previous_by_id = {str(item.get("registration_id") or ""): item for item in previous_entries if item.get("registration_id")}

    rows_list = [dict(row) for row in rows if isinstance(row, dict)]
    eligible_rows = [row for row in rows_list if _eligible(row)]
    eligible_ids = {str(row.get("registration_id") or "") for row in eligible_rows}
    entries: list[dict[str, Any]] = []
    copied = 0
    unchanged = 0
    skipped_missing_files = 0

    for row in eligible_rows:
        registration_id = str(row.get("registration_id") or "")
        previous_entry = previous_by_id.get(registration_id)
        pair_folder = _pair_folder(row, target_root)
        can_reuse = bool(
            previous_entry
            and previous_entry.get("front_sha256") == row.get("image_sha256")
            and previous_entry.get("back_sha256") == row.get("back_image_sha256")
            and pair_folder.is_dir()
            and (target_root / str(previous_entry.get("front_path") or "")).is_file()
            and (target_root / str(previous_entry.get("back_path") or "")).is_file()
            and previous_entry.get("verification_kind") == _verification_kind(row)
        )
        if can_reuse:
            entries.append(previous_entry)
            unchanged += 1
            continue
        entry = _entry_from_row(row, target_root, source_root)
        if entry is None:
            skipped_missing_files += 1
            continue
        entries.append(entry)
        copied += 1

    pruned = 0
    if prune:
        kept_ids = {str(item.get("registration_id") or "") for item in entries}
        for old in previous_entries:
            registration_id = str(old.get("registration_id") or "")
            if registration_id and registration_id not in kept_ids and (registration_id not in eligible_ids or registration_id not in kept_ids):
                pruned += int(_remove_pair_folder(old, target_root))

    entries.sort(key=lambda item: (str(item.get("company")), str(item.get("game")), str(item.get("certification_id"))))
    counts = {company: sum(item.get("company") == company for item in entries) for company in COMPANIES}
    games = {game: sum(item.get("game") == game for item in entries) for game in GAMES}
    payload = {
        "schema_version": 1,
        "patch": PATCH_ID,
        "updated_at": _now(),
        "archive_root": str(target_root),
        "entries": entries,
        "summary": {
            "verified_pairs": len(entries),
            "copied_or_updated": copied,
            "unchanged": unchanged,
            "pruned": pruned,
            "skipped_missing_files": skipped_missing_files,
            "by_company": counts,
            "by_game": games,
            "live_official_verified": sum(item.get("verification_kind") == "live_official_verified" for item in entries),
            "manual_official_reference": sum(item.get("verification_kind") == "manual_official_reference" for item in entries),
        },
        "policy": {
            "front_back_required": True,
            "certificate_required": True,
            "company_grade_required": True,
            "photos_gallery_hidden_with_nomedia": True,
            "slab_reference_learning_only": True,
            "raw_grade_calibration_modified": False,
            "manual_official_reference_is_not_live_official_truth": True,
        },
    }
    atomic_write_json(external_manifest_path, payload, suffix=".verified-archive-manifest.tmp")

    for company in COMPANIES:
        company_dir = target_root / company
        company_dir.mkdir(parents=True, exist_ok=True)
        company_entries = [item for item in entries if item.get("company") == company]
        atomic_write_json(company_dir / "학습목록.json", {
            "schema_version": 1,
            "updated_at": payload["updated_at"],
            "company": company,
            "entries": company_entries,
            "count": len(company_entries),
            "raw_grade_calibration_modified": False,
        }, suffix=".company-learning-list.tmp")
    return payload


def sync_all(*, prune: bool = True) -> dict[str, Any]:
    with manual_photo.LOCK:
        registry = manual_photo._registry()
        rows = [dict(row) for row in registry.get("registrations", []) if isinstance(row, dict)]
    target = archive_root()
    payload = sync_rows(rows, target_root=target, source_root=ROOT, prune=prune)
    internal = dict(payload)
    internal["archive_root"] = str(target)
    atomic_write_json(INTERNAL_MANIFEST, internal, suffix=".verified-archive-index.tmp")
    return payload


def watch(interval: int = 60) -> int:
    interval = max(30, min(int(interval), 3600))
    last_signature = None
    while True:
        try:
            try:
                stat = manual_photo.REGISTRY_PATH.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
            except OSError:
                signature = None
            if signature != last_signature:
                payload = sync_all(prune=True)
                summary = payload.get("summary", {})
                print(json.dumps({"ok": True, "archive_root": payload.get("archive_root"), **summary}, ensure_ascii=False), flush=True)
                last_signature = signature
        except Exception as exc:
            print(json.dumps({"ok": False, "error": type(exc).__name__}, ensure_ascii=False), flush=True)
        time.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sync", action="store_true", help="sync once and exit")
    parser.add_argument("--watch", action="store_true", help="watch registry and keep archive in sync")
    parser.add_argument("--interval", type=int, default=60)
    parser.add_argument("--no-prune", action="store_true")
    args = parser.parse_args()
    if args.watch:
        return watch(args.interval)
    payload = sync_all(prune=not args.no_prune)
    print(json.dumps(payload.get("summary", {}), ensure_ascii=False, indent=2), flush=True)
    print(f"보관 폴더: {payload.get('archive_root')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

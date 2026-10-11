#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Save only certification-bearing front/back graded-card photo pairs.

Automatic collection is deliberately conservative:
- supported game is historical core plus registry-promoted TCGs for manual review only; WATCH never qualifies
- supported grader must be PSA / BGS / CGC / TAG / BRG
- a certification number must already be resolved from listing/OCR evidence
- both front and back photos must be present with explicit pair evidence
- files are saved only to the manual-review area; nothing is auto-registered
- no grading-company certification website is contacted by this module

Android layout (game-only, no grader subfolder):
  Download/TCG등급학습/<game>/
      수동등록목록.json
      수동등록대기/<pair_id>/
          front_candidate.jpg
          back_candidate.jpg
          pair.json

The grader remains in pair.json and the game-level index so PSA/BGS/CGC/TAG/BRG
can still be filtered during manual verification without creating PSA/BGS folders.

Important Android detail:
``/sdcard`` is normally a symbolic-link alias. The shared atomic writer correctly
rejects symlink path components, so this module uses the canonical Android storage
path ``/storage/emulated/0`` and verifies it with the same atomic writer before use.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import time
from typing import Any
from urllib.request import Request

from graded_photo_evidence import normalize_cert
from safe_runtime import (
    atomic_write_bytes,
    atomic_write_json,
    exclusive_file_lock,
    safe_read_text,
    safe_urlopen,
    validate_public_https_url,
)

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "graded_photo_candidates.json"
QUEUE = ROOT / "manual_collected_pair_queue.json"
LOCK_PATH = ROOT / ".manual_pair_queue.watch.lock"
LOCAL_ROOT = ROOT / "GRADE_TRAINING_INBOX" / "collected_pairs"
# Do not use /sdcard here. On Android it is normally a symlink and the shared
# atomic writer intentionally blocks any symlink component for safety.
ANDROID_ROOT = Path("/storage/emulated/0/Download/TCG등급학습")
GAMES = {"pokemon", "onepiece", "naruto"}  # historical/core archive & migration
COMPANIES = {"PSA", "BGS", "CGC", "TAG", "BRG"}


def _reviewable_games(registry_path: Path = ROOT / "tcg_game_registry.json") -> set[str]:
    """Allow verified market-promoted TCGs ONLY into manual-pair quarantine.

    Fail closed to the core three on bad registry. WATCH is never accepted.
    This does not enable grading, official certification, or RAW calibration.
    """
    allowed = set(GAMES)
    try:
        data = json.loads(safe_read_text(registry_path, max_bytes=2_000_000))
    except (OSError, UnicodeError, ValueError, TypeError):
        return allowed
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        return allowed
    games = data.get("games")
    if not isinstance(games, list) or not (0 < len(games) <= 64):
        return allowed
    for row in games:
        if not isinstance(row, dict) or row.get("state") != "promoted":
            continue
        caps, game = row.get("capabilities"), row.get("id")
        if not isinstance(caps, dict) or caps.get("market") is not True or caps.get("grading") is not False:
            continue
        if isinstance(game, str) and re.fullmatch(r"[a-z][a-z0-9-]{1,31}", game):
            allowed.add(game)
    return allowed


REVIEW_GAMES = _reviewable_games()  # candidate intake only, not grade training
MAX_QUEUE = 1000
MAX_SOURCE_RECORDS = 500  # Bound untrusted candidate scans and per-run CPU.
MAX_DOWNLOAD_PAIRS_PER_SYNC = 8  # At most sixteen remote image requests per sync.
MAX_AMBIGUOUS_REVIEW = 100  # Bounded local evidence inbox, not grade training.
MAX_IMAGE_BYTES = 8_000_000
MAX_IMAGE_PIXELS = 36_000_000
INTEGRITY_RECHECK_SECONDS = 900  # Retry failed downloads and discover cache damage without source edits.
UA = "Mozilla/5.0 TCG-Grader-ManualPairQueue/2.2"

PAIR_TEXT_RE = re.compile(
    r"(?:front.{0,40}back|back.{0,40}front|front\s*[/&+]\s*back|"
    r"앞.{0,20}(?:뒤|뒷)|(?:뒤|뒷).{0,20}앞|앞뒷면|전면.{0,20}후면|후면.{0,20}전면|"
    r"表.{0,20}裏|裏.{0,20}表|表裏|両面)",
    re.I,
)
FRONT_TOKEN_RE = re.compile(r"(?:^|[/_.-])(?:front|obverse|face|앞면|전면|表)(?:[/_.-]|$)", re.I)
BACK_TOKEN_RE = re.compile(r"(?:^|[/_.-])(?:back|reverse|rear|뒷면|후면|裏)(?:[/_.-]|$)", re.I)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(safe_read_text(path, max_bytes=24_000_000))
    except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
        return default


def _clean_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text.startswith("https://") or len(text) > 1600:
        return ""
    try:
        validate_public_https_url(text)
    except (OSError, ValueError, TypeError):
        return ""
    return text


def _identity(row: dict[str, Any]) -> tuple[str, str]:
    company = str(row.get("company") or row.get("ocr_company") or "").upper().strip()[:8]
    cert = normalize_cert(row.get("certification_id") or row.get("ocr_certification_id"))
    if company not in COMPANIES or len(cert) < 6:
        return "", ""
    return company, cert


def _distinct_urls(row: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in ("front_image_url", "back_image_url", "image_url"):
        if row.get(key):
            values.append(row.get(key))
    gallery = row.get("image_urls")
    if isinstance(gallery, list):
        values.extend(gallery[:12])
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        url = _clean_url(value)
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _pair_from_row(row: dict[str, Any]) -> tuple[str, str, str] | None:
    front = _clean_url(row.get("front_image_url"))
    back = _clean_url(row.get("back_image_url"))
    if front and back:
        # Conflicting explicit side fields are not evidence for a valid pair.
        return (front, back, "explicit_fields") if front != back else None

    urls = _distinct_urls(row)
    if len(urls) < 2:
        return None

    # A gallery may contain slab details, packaging or several different cards.
    # Never guess which two URLs are card front/back when multiple possibilities
    # exist. Two independent, unambiguous side-labelled URLs are required.
    front_candidates = [url for url in urls
                        if FRONT_TOKEN_RE.search(url) and not BACK_TOKEN_RE.search(url)]
    back_candidates = [url for url in urls
                       if BACK_TOKEN_RE.search(url) and not FRONT_TOKEN_RE.search(url)]
    if len(front_candidates) == 1 and len(back_candidates) == 1:
        return front_candidates[0], back_candidates[0], "url_side_tokens"
    if any(FRONT_TOKEN_RE.search(url) or BACK_TOKEN_RE.search(url) for url in urls):
        return None  # one-sided, conflicting, or multiple side-labelled photos

    text = " ".join((
        str(row.get("title") or ""),
        str(row.get("snippet") or ""),
        str(row.get("description") or ""),
    ))
    if PAIR_TEXT_RE.search(text) and len(urls) == 2:
        return urls[0], urls[1], "listing_declares_front_back"

    return None


def _ambiguous_gallery(row: dict[str, Any]) -> bool:
    """Flag ambiguous multi-image listings for manual source inspection."""
    front = _clean_url(row.get("front_image_url"))
    back = _clean_url(row.get("back_image_url"))
    if front and back:
        return front == back  # conflicting explicit fields need source review
    urls = _distinct_urls(row)
    if len(urls) < 2:
        return False
    front_labeled = [url for url in urls if FRONT_TOKEN_RE.search(url)]
    back_labeled = [url for url in urls if BACK_TOKEN_RE.search(url)]
    if front_labeled or back_labeled:
        return _pair_from_row(row) is None
    label = " ".join((
        str(row.get("title") or ""),
        str(row.get("snippet") or ""),
        str(row.get("description") or ""),
    ))
    return len(urls) > 2 and bool(PAIR_TEXT_RE.search(label))


def _ambiguous_review_record(row: dict[str, Any], game: str,
                             company: str, cert: str) -> dict[str, Any]:
    """A public-source link list for manual side selection; never a photo pair."""
    urls = _distinct_urls(row)[:12]
    source = _clean_url(row.get("url"))
    seed = "\\n".join((game, company, cert, source, *sorted(urls)))
    return {
        "review_id": hashlib.sha256(seed.encode("utf-8", "ignore")).hexdigest()[:20],
        "game": game,
        "company": company,
        "certification_id": cert[:64],
        "card_name": str(row.get("card_name") or row.get("title") or "")[:180],
        "source_listing_url": source,
        "photo_urls": urls[:8],
        "photo_count": len(urls),
        "reason": "ambiguous_front_back_gallery",
        "review_status": "manual_side_selection_required",
        "manual_registration_required": True,
        "automatic_pair_downloaded": False,
        "raw_grade_calibration_eligible": False,
    }


def _saved_ambiguous_review(previous: Any) -> dict[str, dict[str, Any]]:
    """Read a bounded, validated review inbox without trusting old flags."""
    old = previous.get("ambiguous_photo_review_candidates", []) if isinstance(previous, dict) else []
    if not isinstance(old, list):
        return {}
    out = {}
    for item in old[:MAX_AMBIGUOUS_REVIEW]:
        if not isinstance(item, dict):
            continue
        game = item.get("game")
        company, cert = _identity(item)
        identity = item.get("review_id")
        urls = _distinct_urls({"image_urls": item.get("photo_urls")})
        if game not in REVIEW_GAMES or not company or not cert or len(urls) < 2:
            continue
        if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{20}", identity):
            continue
        row = {
            "game": game, "company": company, "certification_id": cert,
            "card_name": str(item.get("card_name") or "")[:180],
            "source_listing_url": _clean_url(item.get("source_listing_url")),
            "photo_urls": urls[:8], "photo_count": len(urls),
            "review_id": identity, "reason": "ambiguous_front_back_gallery",
            "review_status": "manual_side_selection_required",
            "manual_registration_required": True,
            "automatic_pair_downloaded": False,
            "raw_grade_calibration_eligible": False,
        }
        out[identity] = row
    return out


def _pair_key(row: dict[str, Any], front: str, back: str, company: str, cert: str) -> str:
    seed = "\n".join((
        str(row.get("game") or ""), company, cert,
        str(row.get("url") or ""), front, back,
    )).encode("utf-8", "ignore")
    return hashlib.sha256(seed).hexdigest()[:20]


def _pair_folder(target_root: Path, game: str, pair_id: str) -> Path:
    """Return the game-only manual-review folder; never add a grader directory."""
    game = str(game or "").lower()
    if game not in REVIEW_GAMES:
        raise ValueError("unsupported_game")
    pair_id = str(pair_id or "").strip()
    if not re.fullmatch(r"[0-9a-f]{20}", pair_id):
        raise ValueError("invalid_pair_id")
    return target_root / game / "수동등록대기" / pair_id


def _cached_pair_complete(root: Path, game: str, pair_id: str, company: str,
                          cert: str, front_url: str, back_url: str,
                          grade: Any, cached: Any) -> bool:
    """Check actual bounded images + manifest instead of trusting downloaded=True."""
    if not isinstance(cached, dict) or cached.get("downloaded") is not True:
        return False
    try:
        folder = _pair_folder(root, game, pair_id)
        manifest_path = folder / "pair.json"
        if folder.is_symlink() or not folder.is_dir():
            return False
        if manifest_path.is_symlink() or not manifest_path.is_file():
            return False
        manifest = _load(manifest_path, {})
        if not isinstance(manifest, dict):
            return False
        expected = {"pair_id": pair_id, "game": game, "company": company,
                    "certification_id": cert, "front_image_url": front_url,
                    "back_image_url": back_url}
        if any(manifest.get(key) != value for key, value in expected.items()):
            return False
        if str(manifest.get("grade")) != str(grade):
            return False
        if manifest.get("downloaded") is not True or manifest.get("raw_grade_calibration_eligible") is not False:
            return False
        digests = []
        legacy_hashes = {}
        for side, name in (("front", "front_candidate.jpg"), ("back", "back_candidate.jpg")):
            path = folder / name
            if path.is_symlink() or not path.is_file():
                return False
            if not (32 <= path.stat().st_size <= 6_000_000):
                return False
            digest = hashlib.sha256()
            with path.open("rb") as image:
                if image.read(3) != bytes((255, 216, 255)):
                    return False
                image.seek(0)
                for chunk in iter(lambda: image.read(65536), b""):
                    digest.update(chunk)
            value = digest.hexdigest()
            old_hash = manifest.get(side + "_sha256")
            if old_hash not in (None, "", value):
                return False
            if not old_hash:
                legacy_hashes[side + "_sha256"] = value
            digests.append(value)
        if digests[0] == digests[1]:
            return False
        if legacy_hashes:
            # Preserve valid pre-V600 downloads in offline mode, adding only
            # local digest metadata. Do not trigger unnecessary network use.
            updated = dict(manifest)
            updated.update(legacy_hashes)
            try:
                atomic_write_json(manifest_path, updated, suffix=".pair-hash-upgrade.tmp")
            except (OSError, ValueError, TypeError, TimeoutError):
                pass  # content verified this run; next sync can retry metadata upgrade
        return True
    except (OSError, ValueError, TypeError):
        return False


def _target_root() -> tuple[Path, str]:
    """Choose storage only after an atomic-write preflight succeeds.

    A plain ``Path.write_text`` check is insufficient on Android because /sdcard
    can be writable while still being a symlink alias rejected by the secure
    atomic writer. Test the exact writer used for indexes/manifests instead.
    """
    probe: Path | None = None
    try:
        if ANDROID_ROOT.parent.is_dir() and ANDROID_ROOT.parent.exists():
            ANDROID_ROOT.mkdir(parents=True, exist_ok=True)
            probe = ANDROID_ROOT / ".tcg_pair_atomic_write_test.json"
            atomic_write_json(probe, {"ok": True, "probe": "manual_pair_storage"}, suffix=".probe.tmp")
            probe.unlink(missing_ok=True)
            return ANDROID_ROOT, "android_download"
    except (OSError, ValueError, TypeError, TimeoutError):
        if probe is not None:
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                pass

    LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
    local_probe = LOCAL_ROOT / ".tcg_pair_atomic_write_test.json"
    atomic_write_json(local_probe, {"ok": True, "probe": "manual_pair_storage"}, suffix=".probe.tmp")
    local_probe.unlink(missing_ok=True)
    return LOCAL_ROOT, "local_inbox"


def _download_and_normalize(url: str) -> bytes:
    request = Request(url, headers={
        "User-Agent": UA,
        "Accept": "image/avif,image/webp,image/png,image/jpeg;q=0.9,*/*;q=0.1",
    })
    with safe_urlopen(request, timeout=10, max_redirects=3) as response:
        content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].lower().strip()
        raw = response.read(MAX_IMAGE_BYTES + 1)
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("image_too_large")
    if content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise ValueError("unsupported_image_type")

    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    with Image.open(io.BytesIO(raw)) as opened:
        opened.verify()
    with Image.open(io.BytesIO(raw)) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    width, height = image.size
    if width < 320 or height < 320 or width * height > MAX_IMAGE_PIXELS:
        raise ValueError("invalid_image_dimensions")
    scale = min(1.0, 2200.0 / max(width, height))
    if scale < 1.0:
        image = image.resize((max(320, round(width * scale)), max(320, round(height * scale))))
    out = io.BytesIO()
    for quality in (90, 84, 78, 72):
        out.seek(0)
        out.truncate(0)
        image.save(out, format="JPEG", quality=quality, optimize=True)
        if out.tell() <= 6_000_000:
            return out.getvalue()
    raise ValueError("normalized_image_too_large")


def _existing_entries() -> dict[str, dict[str, Any]]:
    payload = _load(QUEUE, {"pairs": []})
    rows = payload.get("pairs", []) if isinstance(payload, dict) else []
    return {
        str(row.get("pair_id")): dict(row)
        for row in rows
        if isinstance(row, dict) and row.get("pair_id")
    }


def _legacy_index_is_empty(path: Path) -> bool:
    """Only known-empty legacy indexes can be removed; preserve uncertain data."""
    value = _load(path, None)
    if not isinstance(value, dict) or not set(value).issubset({"count", "pairs"}):
        return False
    if type(value.get("count", 0)) is not int or value.get("count", 0) != 0:
        return False
    return value.get("pairs", []) == []


def _migrate_legacy_grader_layout(target_root: Path) -> dict[str, int]:
    """Move legacy grading folders without ever discarding unverified old indexes.

    Existing legacy index records may be the only surviving inventory when a
    directory move fails, collides, or is absent from the current queue.
    Keep such indexes for manual recovery rather than deleting them.
    """
    moved = 0
    collisions = 0
    removed_indexes = 0
    preserved_indexes = 0
    unsafe_symlinks_skipped = 0
    for game in sorted(GAMES):
        game_root = target_root / game
        if game_root.is_symlink():
            unsafe_symlinks_skipped += 1
            continue
        game_root.mkdir(parents=True, exist_ok=True)
        new_wait = game_root / "수동등록대기"
        if new_wait.is_symlink():
            unsafe_symlinks_skipped += 1
            continue
        new_wait.mkdir(parents=True, exist_ok=True)
        for company in sorted(COMPANIES):
            legacy = game_root / company
            legacy_wait = legacy / "수동등록대기"
            if legacy.is_symlink() or legacy_wait.is_symlink():
                unsafe_symlinks_skipped += 1
                continue
            if legacy_wait.is_dir():
                for child in list(legacy_wait.iterdir()):
                    if child.is_symlink():
                        unsafe_symlinks_skipped += 1
                        continue
                    if not child.is_dir() or not re.fullmatch(r"[0-9a-f]{20}", child.name):
                        continue
                    destination = new_wait / child.name
                    if destination.exists() or destination.is_symlink():
                        collisions += 1
                        continue
                    try:
                        shutil.move(str(child), str(destination))
                        moved += 1
                    except OSError:
                        continue
            legacy_index = legacy / "수동등록목록.json"
            if legacy_index.is_file() and not legacy_index.is_symlink():
                try:
                    # Any residual files, even unknown names, may be needed to
                    # recover a user's old photo collection.
                    legacy_has_children = legacy_wait.is_dir() and any(legacy_wait.iterdir())
                except OSError:
                    legacy_has_children = True
                if legacy_has_children or not _legacy_index_is_empty(legacy_index):
                    preserved_indexes += 1
                else:
                    try:
                        legacy_index.unlink()
                        removed_indexes += 1
                    except OSError:
                        preserved_indexes += 1
            for folder in (legacy_wait, legacy):
                try:
                    folder.rmdir()
                except OSError:
                    pass
    return {
        "legacy_pairs_moved": moved,
        "legacy_collisions": collisions,
        "legacy_indexes_removed": removed_indexes,
        "legacy_indexes_preserved": preserved_indexes,
        "legacy_symlink_paths_skipped": unsafe_symlinks_skipped,
    }

def _write_group_indexes(target_root: Path, pairs: list[dict[str, Any]],
                         ambiguous_review: list[dict[str, Any]] | None = None) -> None:
    grouped: dict[str, list[dict[str, Any]]] = {game: [] for game in GAMES}
    for row in pairs:
        if not isinstance(row, dict):
            continue
        game = str(row.get("game") or "").lower()
        company = str(row.get("company") or "").upper()
        if game in REVIEW_GAMES and company in COMPANIES:
            grouped.setdefault(game, []).append(row)
    # Manual-only ambiguous review sources are genuine nonempty per-game work.
    # A promoted-game folder can appear when its review inbox has records.
    ambiguous_by_game: dict[str, list[dict[str, Any]]] = {}
    for item in (ambiguous_review or []):
        game = item.get("game") if isinstance(item, dict) else None
        if game in REVIEW_GAMES:
            ambiguous_by_game.setdefault(game, []).append(item)
            grouped.setdefault(game, [])
    # No blank promoted-game directories on tablets.
    for game in sorted(grouped):
        folder = target_root / game
        folder.mkdir(parents=True, exist_ok=True)
        rows = grouped.get(game, [])
        photo_review = ambiguous_by_game.get(game, [])
        by_company = {company: 0 for company in sorted(COMPANIES)}
        for row in rows:
            company = str(row.get("company") or "").upper()
            if company in by_company:
                by_company[company] += 1
        # The inventory is not proof that cached front/back photos are intact.
        # Only mark ready when THIS sync verified both files or saved a new pair.
        ready = sum(row.get("local_files_verified_this_sync") is True for row in rows)
        redownload = sum(row.get("review_status") == "needs_redownload" for row in rows)
        index = {
            "ok": True,
            "updated_at": _now(),
            "game": game,
            "count": len(rows),
            "visible_count": min(500, len(rows)),
            "truncated": len(rows) > 500,
            "verified_local_photo_pairs": ready,
            "needs_redownload_count": redownload,
            "ambiguous_photo_manual_review_count": len(photo_review),
            "ambiguous_photo_manual_review": photo_review[:MAX_AMBIGUOUS_REVIEW],
            "not_checked_this_sync_count": len(rows) - ready - redownload,
            "by_company": by_company,
            "manual_registration_required": True,
            "automatic_registration": False,
            "automatic_official_lookup": False,
            "storage_layout": "game_only",
            "pairs": [{
                "pair_id": row.get("pair_id"),
                "company": row.get("company"),
                "certification_id": row.get("certification_id"),
                "grade": row.get("grade"),
                "card_name": row.get("card_name"),
                "folder": row.get("folder"),
                "source_listing_url": row.get("source_listing_url"),
                "downloaded_metadata": row.get("downloaded") is True,
                "local_files_verified_this_sync": row.get("local_files_verified_this_sync") is True,
                "review_status": row.get("review_status") or "not_checked_this_sync",
                "manual_registration_required": True,
                "raw_grade_calibration_eligible": False,
            } for row in rows[:500]],
        }
        atomic_write_json(folder / "수동등록목록.json", index, suffix=".manual-index.tmp")


def sync_once() -> dict[str, Any]:
    payload = _load(SOURCE, {})
    rows = payload.get("records", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        rows = []
    source_records_total = len(rows)
    previous = _load(QUEUE, {})
    ambiguous_reviews = _saved_ambiguous_review(previous)
    scan_remembered = previous.get("scan_cursor", 0) if isinstance(previous, dict) else 0
    if type(scan_remembered) is not int or scan_remembered < 0:
        scan_remembered = 0
    scan_cursor = scan_remembered % len(rows) if rows else 0
    # Inspect every source record over successive runs, not just the first
    # MAX_SOURCE_RECORDS. No permanent starvation beyond the scan budget.
    rows = (rows[scan_cursor:] + rows[:scan_cursor])[:MAX_SOURCE_RECORDS]
    next_scan_cursor = (scan_cursor + len(rows)) % source_records_total if source_records_total else 0
    remembered = previous.get("download_cursor", 0) if isinstance(previous, dict) else 0
    if type(remembered) is not int or remembered < 0:
        remembered = 0
    cursor = remembered % len(rows) if rows else 0
    rotated = rows[cursor:] + rows[:cursor]
    target_root, storage_mode = _target_root()
    migration = _migrate_legacy_grader_layout(target_root)
    existing = _existing_entries()
    seen_candidates = 0
    pair_candidates = 0
    newly_saved = 0
    skipped_existing = 0
    skipped_missing_identity = 0
    skipped_missing_pair = 0
    skipped_ambiguous_gallery = 0
    failed = 0
    cache_repair_attempts = 0
    cache_repair_failures = 0
    download_attempts = 0
    deferred_downloads = 0
    next_cursor = cursor
    by_game = {
        game: {"seen": 0, "missing_cert": 0, "missing_pair": 0,
               "pair_candidates": 0, "cached_complete": 0,
               "ambiguous_gallery": 0, "repair_attempts": 0,
               "saved": 0, "failed": 0}
        for game in sorted(REVIEW_GAMES)
    }
    errors: list[dict[str, Any]] = []
    verified_ids: set[str] = set()

    for position, raw in enumerate(rotated):
        if not isinstance(raw, dict):
            continue
        game = str(raw.get("game") or "").lower()
        if game not in REVIEW_GAMES:
            continue
        seen_candidates += 1
        by_game[game]["seen"] += 1
        company, cert = _identity(raw)
        if not company or not cert:
            skipped_missing_identity += 1
            by_game[game]["missing_cert"] += 1
            continue
        pair = _pair_from_row(raw)
        if pair is None:
            skipped_missing_pair += 1
            by_game[game]["missing_pair"] += 1
            if _ambiguous_gallery(raw):
                skipped_ambiguous_gallery += 1
                by_game[game]["ambiguous_gallery"] += 1
                review = _ambiguous_review_record(raw, game, company, cert)
                # Keep only the newest one hundred distinct source evidence
                # bundles. No photos are downloaded or auto-graded here.
                ambiguous_reviews.pop(review["review_id"], None)
                ambiguous_reviews[review["review_id"]] = review
                while len(ambiguous_reviews) > MAX_AMBIGUOUS_REVIEW:
                    ambiguous_reviews.pop(next(iter(ambiguous_reviews)))
            continue
        front_url, back_url, evidence = pair
        pair_candidates += 1
        by_game[game]["pair_candidates"] += 1
        pair_id = _pair_key(raw, front_url, back_url, company, cert)
        prior = existing.get(pair_id)
        if _cached_pair_complete(target_root, game, pair_id, company, cert,
                                 front_url, back_url, raw.get("grade"), prior):
            skipped_existing += 1
            verified_ids.add(pair_id)
            by_game[game]["cached_complete"] += 1
            continue
        if isinstance(prior, dict) and prior.get("downloaded") is True:
            # Keep stale metadata as a repair record, never a completed pair.
            prior["downloaded"] = False
            prior["needs_redownload"] = True
            prior["raw_grade_calibration_eligible"] = False
            cache_repair_attempts += 1
            by_game[game]["repair_attempts"] += 1
        if download_attempts >= MAX_DOWNLOAD_PAIRS_PER_SYNC:
            deferred_downloads += 1
            continue
        download_attempts += 1
        if rows:
            next_cursor = (cursor + position + 1) % len(rows)

        folder = _pair_folder(target_root, game, pair_id)
        front_path = folder / "front_candidate.jpg"
        back_path = folder / "back_candidate.jpg"
        manifest_path = folder / "pair.json"
        try:
            front_bytes = _download_and_normalize(front_url)
            back_bytes = _download_and_normalize(back_url)
            if hashlib.sha256(front_bytes).digest() == hashlib.sha256(back_bytes).digest():
                raise ValueError("front_back_images_identical")
            folder.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(front_path, front_bytes, suffix=".front.tmp")
            atomic_write_bytes(back_path, back_bytes, suffix=".back.tmp")
            item = {
                "pair_id": pair_id,
                "created_at": _now(),
                "game": game,
                "company": company,
                "grade": raw.get("grade"),
                "certification_id": cert,
                "card_name": str(raw.get("card_name") or raw.get("title") or "")[:260],
                "source": str(raw.get("source") or "")[:120],
                "source_listing_url": str(raw.get("url") or "")[:1600],
                "front_image_url": front_url,
                "back_image_url": back_url,
                "front_sha256": hashlib.sha256(front_bytes).hexdigest(),
                "back_sha256": hashlib.sha256(back_bytes).hexdigest(),
                "pair_evidence": evidence,
                "orientation_requires_manual_confirmation": evidence == "listing_declares_front_back",
                "front_local_path": str(front_path),
                "back_local_path": str(back_path),
                "manifest_local_path": str(manifest_path),
                "folder": str(folder),
                "storage_mode": storage_mode,
                "storage_layout": "game_only",
                "downloaded": True,
                "identity_gate": "supported_grader_plus_certification_number",
                "front_back_gate": "both_required",
                "manual_registration_required": True,
                "automatic_registration": False,
                "automatic_official_lookup": False,
                "official_verification_mode": "user_browser_manual",
                "raw_grade_calibration_eligible": False,
            }
            atomic_write_json(manifest_path, item, suffix=".pair-manifest.tmp")
            existing[pair_id] = item
            verified_ids.add(pair_id)
            newly_saved += 1
            by_game[game]["saved"] += 1
        except (OSError, ValueError, TypeError, TimeoutError) as exc:
            failed += 1
            by_game[game]["failed"] += 1
            if isinstance(prior, dict) and prior.get("needs_redownload") is True:
                cache_repair_failures += 1
            errors.append({
                "pair_id": pair_id, "game": game, "company": company,
                "certification_id": cert, "error": type(exc).__name__,
                "reason": str(exc)[:160],
            })

    if rows and download_attempts == 0:
        next_cursor = (cursor + min(len(rows), MAX_DOWNLOAD_PAIRS_PER_SYNC)) % len(rows)
    pairs = sorted(existing.values(), key=lambda row: str(row.get("created_at") or ""), reverse=True)[:MAX_QUEUE]
    # Re-point migrated queue metadata to the current game-only path so the index
    # does not keep stale <game>/<grader> folder strings from previous versions.
    for row in pairs:
        pair_id = str(row.get("pair_id") or "")
        game = str(row.get("game") or "").lower()
        verified_now = pair_id in verified_ids
        row["local_files_verified_this_sync"] = verified_now
        row["review_status"] = (
            "photo_files_ready" if verified_now
            else "needs_redownload" if row.get("needs_redownload") is True
            else "not_checked_this_sync"
        )
        # A previously downloaded record without a currently matching source
        # must not be advertised as a verified photo pair.
        row["raw_grade_calibration_eligible"] = False
        if game in REVIEW_GAMES and re.fullmatch(r"[0-9a-f]{20}", pair_id):
            current_folder = _pair_folder(target_root, game, pair_id)
            if current_folder.is_dir():
                row["folder"] = str(current_folder)
                row["front_local_path"] = str(current_folder / "front_candidate.jpg")
                row["back_local_path"] = str(current_folder / "back_candidate.jpg")
                row["manifest_local_path"] = str(current_folder / "pair.json")
                row["storage_layout"] = "game_only"
    review_candidates = list(ambiguous_reviews.values())
    _write_group_indexes(target_root, pairs, review_candidates)
    result = {
        "ok": True,
        "schema_version": 4,
        "updated_at": _now(),
        "storage_mode": storage_mode,
        "target_root": str(target_root),
        "download_cursor": next_cursor,
        "scan_cursor": next_scan_cursor,
        "summary": {
            "source_records_total": source_records_total,
            "source_records_examined": len(rows),
            "source_records_over_limit": source_records_total - len(rows),
            "network_pair_attempts": download_attempts,
            "network_pair_attempt_limit": MAX_DOWNLOAD_PAIRS_PER_SYNC,
            "network_pair_attempts_deferred": deferred_downloads,
            "game_candidates_seen": seen_candidates,
            "certified_front_back_pair_candidates": pair_candidates,
            "newly_saved_pairs": newly_saved,
            "existing_pairs_skipped": skipped_existing,
            "missing_grader_or_cert_skipped": skipped_missing_identity,
            "missing_front_back_pair_skipped": skipped_missing_pair,
            "ambiguous_multi_photo_gallery_skipped": skipped_ambiguous_gallery,
            "ambiguous_photo_review_queue_size": len(review_candidates),
            "failed_pairs": failed,
            "cache_repair_attempts": cache_repair_attempts,
            "cache_repair_failures": cache_repair_failures,
            "game_candidate_diagnostics": by_game,
            "total_manual_pairs": len(pairs),
            "downloaded_metadata_pairs": sum(
                1 for p in pairs if p.get("downloaded") is True
            ),
            "verified_local_pairs_this_sync": sum(
                p.get("local_files_verified_this_sync") is True for p in pairs
            ),
            "not_checked_this_sync_pairs": sum(
                p.get("review_status") == "not_checked_this_sync" for p in pairs
            ),
            "redownload_needed_pairs": sum(
                1 for p in pairs if p.get("needs_redownload") is True
                and p.get("downloaded") is not True
            ),
            "automatic_registration_attempts": 0,
            "automatic_official_lookup_attempts": 0,
            **migration,
        },
        "pairs": pairs,
        "ambiguous_photo_review_candidates": review_candidates,
        "errors": errors[:100],
        "policy": {
            "supported_game_required": True,
            "promoted_game_manual_review_only": True,
            "watch_game_collection_disabled": True,
            "promoted_game_auto_calibration": False,
            "supported_grader_required": True,
            "certification_number_required": True,
            "front_and_back_required": True,
            "ambiguous_gallery_requires_manual_review": True,
            "ambiguous_gallery_review_record_saved": True,
            "ambiguous_gallery_never_autodownloaded": True,
            "single_photo_candidate_saved": False,
            "automatic_registration": False,
            "automatic_official_lookup": False,
            "cached_pair_files_revalidated": True,
            "cached_pair_sha256_checked": True,
            "game_level_candidate_diagnostics": True,
            "inventory_separates_verified_repair_and_unchecked": True,
            "bounded_network_photo_pair_attempts": True,
            "round_robin_photo_pair_intake": True,
            "rotating_source_scan_window": True,
            "manual_site_verification_required": True,
            "grouped_by_game_only": True,
            "grader_subfolders_created": False,
            "grader_preserved_in_manifest_and_index": True,
            "android_symlink_alias_avoided": True,
            "atomic_storage_preflight_required": True,
            "raw_grade_calibration_eligible": False,
        },
    }
    atomic_write_json(QUEUE, result, suffix=".manual-pair-queue.tmp")
    return result


def _source_signature() -> tuple[int, int] | None:
    try:
        stat = SOURCE.stat()
        return (stat.st_mtime_ns, stat.st_size)
    except OSError:
        return None


def _watch_cycle(last_signature, *, integrity_due: bool = False):
    signature = _source_signature()
    if signature == last_signature and not integrity_due:
        return last_signature, None
    result = sync_once()
    # The same source may need another sync when a downloaded front/back JPEG
    # disappears, changes, or could not be fetched last time. A periodic sweep
    # must therefore bypass the source-file timestamp shortcut.
    # Only an acknowledged successful sync updates the source signature.
    return signature, result


def watch(interval: int, *, recheck_seconds: int = INTEGRITY_RECHECK_SECONDS) -> int:
    interval = max(30, min(900, int(interval)))
    recheck_seconds = max(300, min(86400, int(recheck_seconds)))
    last_signature: tuple[int, int] | None = None
    last_integrity_check: float | None = None
    with exclusive_file_lock(LOCK_PATH, timeout_seconds=0.05, stale_seconds=7200):
        while True:
            now = time.monotonic()
            integrity_due = (
                last_integrity_check is None
                or now - last_integrity_check >= recheck_seconds
                or now < last_integrity_check  # monotonic guard, e.g. clock reset in test VM
            )
            try:
                last_signature, result = _watch_cycle(last_signature, integrity_due=integrity_due)
                if isinstance(result, dict):
                    last_integrity_check = now
                    print(json.dumps(result["summary"], ensure_ascii=False), flush=True)
            except Exception as exc:
                # Do not acknowledge a failed recheck. Retry at the next polling
                # interval, even when the candidates JSON did not change.
                print(json.dumps({
                    "ok": False,
                    "error": type(exc).__name__,
                    "message": str(exc)[:240],
                    "retry_next_interval": True,
                }, ensure_ascii=False), flush=True)
            time.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser(description="인증번호가 있는 앞면+뒷면 등급사진 후보를 등록 게임별로 수동검토 대기 저장합니다. 공식 RAW 학습은 수행하지 않습니다.")
    parser.add_argument("--watch", action="store_true", help="graded_photo_candidates.json 변경을 계속 감시")
    parser.add_argument("--interval", type=int, default=60, help="감시 간격(초)")
    parser.add_argument("--recheck-seconds", type=int, default=INTEGRITY_RECHECK_SECONDS,
                        help="후보 파일 변경과 무관한 사진쌍 정기 무결성 검사 간격(초, 기본 900)")
    args = parser.parse_args()
    if args.watch:
        return watch(args.interval, recheck_seconds=args.recheck_seconds)
    result = sync_once()
    print(json.dumps(result["summary"], ensure_ascii=False))
    print("수동등록 폴더:", result["target_root"])
    print("저장 구조: <게임>/수동등록대기/<카드> (PSA/BGS 등급사 하위폴더 없음)")
    if result["storage_mode"] != "android_download":
        print("[경고] Android Download 저장소를 사용할 수 없어 앱 내부 폴더를 사용 중입니다. Termux 저장소 권한을 확인하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

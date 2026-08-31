#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Save only certification-bearing front/back graded-card photo pairs.

Automatic collection is deliberately conservative:
- supported game must be Pokemon / One Piece / Naruto
- supported grader must be PSA / BGS / CGC / TAG / BRG
- a certification number must already be resolved from listing/OCR evidence
- both front and back photos must be present with explicit pair evidence
- files are saved only to the manual-review area; nothing is auto-registered
- no grading-company certification website is contacted by this module

Android layout:
  Download/TCG등급학습/<game>/<grader>/수동등록대기/<pair_id>/
      front_candidate.jpg
      back_candidate.jpg
      pair.json
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
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
ANDROID_ROOT = Path("/sdcard/Download/TCG등급학습")
GAMES = {"pokemon", "onepiece", "naruto"}
COMPANIES = {"PSA", "BGS", "CGC", "TAG", "BRG"}
MAX_QUEUE = 1000
MAX_IMAGE_BYTES = 8_000_000
MAX_IMAGE_PIXELS = 36_000_000
UA = "Mozilla/5.0 TCG-Grader-ManualPairQueue/2.0"

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
    if front and back and front != back:
        return front, back, "explicit_fields"

    urls = _distinct_urls(row)
    if len(urls) < 2:
        return None

    front_candidates = [url for url in urls if FRONT_TOKEN_RE.search(url)]
    back_candidates = [url for url in urls if BACK_TOKEN_RE.search(url)]
    for front_url in front_candidates:
        for back_url in back_candidates:
            if front_url != back_url:
                return front_url, back_url, "url_side_tokens"

    text = " ".join((
        str(row.get("title") or ""),
        str(row.get("snippet") or ""),
        str(row.get("description") or ""),
    ))
    if PAIR_TEXT_RE.search(text):
        return urls[0], urls[1], "listing_declares_front_back"

    return None


def _pair_key(row: dict[str, Any], front: str, back: str, company: str, cert: str) -> str:
    seed = "\n".join((
        str(row.get("game") or ""), company, cert,
        str(row.get("url") or ""), front, back,
    )).encode("utf-8", "ignore")
    return hashlib.sha256(seed).hexdigest()[:20]


def _target_root() -> tuple[Path, str]:
    try:
        if ANDROID_ROOT.parent.is_dir() and ANDROID_ROOT.parent.exists():
            ANDROID_ROOT.mkdir(parents=True, exist_ok=True)
            probe = ANDROID_ROOT / ".tcg_pair_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return ANDROID_ROOT, "android_download"
    except OSError:
        pass
    LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
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


def _write_group_indexes(target_root: Path, pairs: list[dict[str, Any]]) -> None:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in pairs:
        if not isinstance(row, dict):
            continue
        game = str(row.get("game") or "").lower()
        company = str(row.get("company") or "").upper()
        if game in GAMES and company in COMPANIES:
            grouped.setdefault((game, company), []).append(row)
    for game in GAMES:
        for company in COMPANIES:
            folder = target_root / game / company
            folder.mkdir(parents=True, exist_ok=True)
            rows = grouped.get((game, company), [])
            index = {
                "ok": True,
                "updated_at": _now(),
                "game": game,
                "company": company,
                "count": len(rows),
                "manual_registration_required": True,
                "automatic_registration": False,
                "automatic_official_lookup": False,
                "pairs": [{
                    "pair_id": row.get("pair_id"),
                    "certification_id": row.get("certification_id"),
                    "grade": row.get("grade"),
                    "card_name": row.get("card_name"),
                    "folder": row.get("folder"),
                    "source_listing_url": row.get("source_listing_url"),
                } for row in rows[:500]],
            }
            atomic_write_json(folder / "수동등록목록.json", index, suffix=".manual-index.tmp")


def sync_once() -> dict[str, Any]:
    payload = _load(SOURCE, {})
    rows = payload.get("records", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        rows = []
    target_root, storage_mode = _target_root()
    existing = _existing_entries()
    seen_candidates = 0
    pair_candidates = 0
    newly_saved = 0
    skipped_existing = 0
    skipped_missing_identity = 0
    skipped_missing_pair = 0
    failed = 0
    errors: list[dict[str, Any]] = []

    for raw in rows:
        if not isinstance(raw, dict):
            continue
        game = str(raw.get("game") or "").lower()
        if game not in GAMES:
            continue
        seen_candidates += 1
        company, cert = _identity(raw)
        if not company or not cert:
            skipped_missing_identity += 1
            continue
        pair = _pair_from_row(raw)
        if pair is None:
            skipped_missing_pair += 1
            continue
        front_url, back_url, evidence = pair
        pair_candidates += 1
        pair_id = _pair_key(raw, front_url, back_url, company, cert)
        if pair_id in existing and existing[pair_id].get("downloaded") is True:
            skipped_existing += 1
            continue

        folder = target_root / game / company / "수동등록대기" / pair_id
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
                "pair_evidence": evidence,
                "orientation_requires_manual_confirmation": evidence == "listing_declares_front_back",
                "front_local_path": str(front_path),
                "back_local_path": str(back_path),
                "manifest_local_path": str(manifest_path),
                "folder": str(folder),
                "storage_mode": storage_mode,
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
            newly_saved += 1
        except (OSError, ValueError, TypeError, TimeoutError) as exc:
            failed += 1
            errors.append({
                "pair_id": pair_id, "game": game, "company": company,
                "certification_id": cert, "error": type(exc).__name__,
                "reason": str(exc)[:160],
            })

    pairs = sorted(existing.values(), key=lambda row: str(row.get("created_at") or ""), reverse=True)[:MAX_QUEUE]
    _write_group_indexes(target_root, pairs)
    result = {
        "ok": True,
        "schema_version": 2,
        "updated_at": _now(),
        "storage_mode": storage_mode,
        "target_root": str(target_root),
        "summary": {
            "game_candidates_seen": seen_candidates,
            "certified_front_back_pair_candidates": pair_candidates,
            "newly_saved_pairs": newly_saved,
            "existing_pairs_skipped": skipped_existing,
            "missing_grader_or_cert_skipped": skipped_missing_identity,
            "missing_front_back_pair_skipped": skipped_missing_pair,
            "failed_pairs": failed,
            "total_manual_pairs": len(pairs),
            "automatic_registration_attempts": 0,
            "automatic_official_lookup_attempts": 0,
        },
        "pairs": pairs,
        "errors": errors[:100],
        "policy": {
            "supported_game_required": True,
            "supported_grader_required": True,
            "certification_number_required": True,
            "front_and_back_required": True,
            "single_photo_candidate_saved": False,
            "automatic_registration": False,
            "automatic_official_lookup": False,
            "manual_site_verification_required": True,
            "grouped_by_game_and_grader": True,
            "raw_grade_calibration_eligible": False,
        },
    }
    atomic_write_json(QUEUE, result, suffix=".manual-pair-queue.tmp")
    return result


def watch(interval: int) -> int:
    interval = max(30, min(900, int(interval)))
    last_signature: tuple[int, int] | None = None
    with exclusive_file_lock(LOCK_PATH, timeout_seconds=0.05, stale_seconds=7200):
        while True:
            try:
                stat = SOURCE.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
            except OSError:
                signature = None
            if signature != last_signature:
                try:
                    result = sync_once()
                    print(json.dumps(result["summary"], ensure_ascii=False), flush=True)
                except Exception as exc:
                    print(json.dumps({"ok": False, "error": type(exc).__name__}, ensure_ascii=False), flush=True)
                last_signature = signature
            time.sleep(interval)


def main() -> int:
    parser = argparse.ArgumentParser(description="인증번호가 있는 앞면+뒷면 등급사진만 게임/등급사별 수동등록 폴더로 저장합니다.")
    parser.add_argument("--watch", action="store_true", help="graded_photo_candidates.json 변경을 계속 감시")
    parser.add_argument("--interval", type=int, default=60, help="감시 간격(초)")
    args = parser.parse_args()
    if args.watch:
        return watch(args.interval)
    result = sync_once()
    print(json.dumps(result["summary"], ensure_ascii=False))
    print("수동등록 폴더:", result["target_root"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

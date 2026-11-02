"""Bounded private, reciprocal image/catalog recheck plan (V887).

Never modifies, downloads, promotes, relabels, or deletes image/catalog evidence.
A finished recheck is recognized ONLY by a current exact-ID catalog match.
Source coverage sweeps and TCGdex metadata retries remain with existing workers.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

import tablet_image_library_v1 as library

SCHEMA = "tablet-private-image-reciprocity/v887"
FILENAME = "collection_image_reciprocity_v887.json"
MAX_TASKS = 3000
MAX_HISTORY = 128
MAX_BYTES = 2_000_000
MAX_PRIORITY = 10000
HEX32 = re.compile(r"^[a-f0-9]{32}$")
REGIONS = frozenset(("KR", "JP", "US", "CN-S", "CN-T"))
ALLOWED_DIRECTIONS = frozenset(("IMAGE_NEEDS_METADATA", "CATALOG_NEEDS_IMAGE"))
BLOCKED = frozenset(("AMBIGUOUS_CODE", "CARD_VARIANT_CONFLICT",
                     "CARD_SET_CONFLICT", "DATASET_INCOMPLETE",
                     "SOURCE_RECHECK_REQUIRED", "CARD_VARIANT_EVIDENCE_INCOMPLETE",
                     "CARD_SET_EVIDENCE_INCOMPLETE"))
# Existing provider coverage; no additions or synthetic supported locales.
PROVIDER_COVERAGE = frozenset((
    ("pokemon", "JP"), ("pokemon", "US"), ("pokemon", "CN-T"),
    ("onepiece", "JP"), ("onepiece", "US"), ("onepiece", "CN-T"),
    ("mtg", "KR"), ("mtg", "JP"), ("mtg", "US"), ("mtg", "CN-S"), ("mtg", "CN-T"),
    ("yugioh", "US"), ("lorcana", "US"), ("swu", "US"),
    ("gundam", "US"), ("riftbound", "US"),
))


def _id(task):
    if not isinstance(task, dict) or task.get("direction") not in ALLOWED_DIRECTIONS:
        return ""
    field = "image_id" if task["direction"] == "IMAGE_NEEDS_METADATA" else "source_record_id"
    value = task.get(field)
    if not isinstance(value, str) or not HEX32.fullmatch(value):
        return ""
    return task["direction"] + ":" + value


def _read(root):
    file = root / FILENAME
    if file.is_symlink():
        raise ValueError("unsafe_reconciliation_symlink")
    if not file.exists():
        return {"schema": SCHEMA, "tasks": [], "history": []}
    if not file.is_file() or file.stat().st_size > MAX_BYTES:
        raise ValueError("reconciliation_file_limit")
    def unique_pairs(pairs):
        out = {}
        for key, val in pairs:
            if key in out:
                raise ValueError("reconciliation_duplicate_key")
            out[key] = val
        return out
    obj = json.loads(file.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
    if not isinstance(obj, dict) or obj.get("schema") != SCHEMA:
        raise ValueError("reconciliation_schema")
    for field, max_rows in (("tasks", MAX_TASKS), ("history", MAX_HISTORY)):
        value = obj.get(field)
        if not isinstance(value, list) or len(value) > max_rows:
            raise ValueError("reconciliation_invalid_" + field)
        for row in value:
            if not isinstance(row, dict) or not _id(row):
                raise ValueError("reconciliation_invalid_item")
    return obj


def _valid_report(report):
    if not isinstance(report, dict) or report.get("ok") is not True:
        return False
    if report.get("source_errors") or report.get("summary", {}).get("queue_truncated"):
        return False
    if report.get("summary", {}).get("source_limit_reached"):
        return False
    queue = report.get("gap_queue")
    return isinstance(queue, list) and len(queue) <= MAX_TASKS


def _action(task, image_map, source_map):
    reason = task.get("reason", "")
    direction = task["direction"]
    if reason in BLOCKED:
        return "REVIEW_EXACT_IDENTITY"
    if direction == "IMAGE_NEEDS_METADATA":
        image = image_map.get(task["image_id"], {})
        source_id = image.get("source_id", "")
        if (reason == "CARD_METADATA_INCOMPLETE" and
                image.get("origin", "auto") == "auto" and
                image.get("provider") == "TCGdex" and
                image.get("game_id") == "pokemon" and
                image.get("kind") in ("CARD", "PROMO") and
                isinstance(source_id, str) and
                any(source_id.startswith("pokemon/" + loc + "/")
                    for loc in ("ja", "en", "zh-tw"))):
            return "EXISTING_PROVIDER_METADATA_RETRY"
        return "REVIEW_IMAGE_IDENTIFIER"
    source = source_map.get(task["source_record_id"], {})
    key = (task.get("game_id"), task.get("region"))
    codes = task.get("product_codes")
    if (key in PROVIDER_COVERAGE and source.get("source_health") == "HEALTHY" and
            isinstance(codes, list) and len(codes) == 1 and
            isinstance(codes[0], str) and codes[0]):
        return "PRIORITIZE_APPROVED_PROVIDER_COVERAGE"
    return "REVIEW_SOURCE_AND_EDITION"


def priority_from_report(report, repeated=()):
    """Steer existing round-robin; never request URLs or select a card picture."""
    if not _valid_report(report):
        return {}
    base = {}
    for row in report.get("collection_priorities", []):
        if not isinstance(row, dict):
            continue
        key = (row.get("game_id"), row.get("region"))
        number = row.get("missing_images")
        if key in PROVIDER_COVERAGE and type(number) is int and number > 0:
            base[key] = min(MAX_PRIORITY, number)
    images = {r["id"]: r for r in report.get("local_catalog", [])
              if isinstance(r, dict) and isinstance(r.get("id"), str)}
    sources = {r["source_record_id"]: r for r in report.get("source_catalog", [])
               if isinstance(r, dict) and isinstance(r.get("source_record_id"), str)}
    # First observation gets the historical base score. Only an independently
    # persisted, still-present gap in 2+ completed cycles gets a retry bonus.
    repeated = set(repeated)
    for task in report["gap_queue"]:
        if (_id(task) in repeated and
                _action(task, images, sources) == "PRIORITIZE_APPROVED_PROVIDER_COVERAGE"):
            key = (task.get("game_id"), task.get("region"))
            if key in PROVIDER_COVERAGE and key in base:
                base[key] = min(MAX_PRIORITY, base[key] + 2)
    return base


def repeated_priority_ids(*, root=None):
    """Only completed local recurrence, never a transient or duplicate mismatch."""
    try:
        root = Path(root) if root is not None else library.storage_root()
        with library.LOCK:
            plan = _read(root)
        return frozenset(_id(row) for row in plan["tasks"]
                         if (row.get("recheck_action") ==
                             "PRIORITIZE_APPROVED_PROVIDER_COVERAGE"
                             and row.get("status") == "AUTOMATIC_RECHECK_ELIGIBLE"
                             and type(row.get("observed_cycles")) is int
                             and 2 <= row["observed_cycles"] <= 1000000))
    except (OSError, ValueError, TypeError, UnicodeError):
        return frozenset()


def write_plan(report, *, root=None):
    """Persist auditable next actions; sidecar only, no original index mutation."""
    if not _valid_report(report):
        return {"ok": False, "status": "HOLD_INCOMPLETE_REPORT"}
    root = Path(root) if root is not None else library.storage_root()
    stamp = datetime.now(timezone.utc).isoformat()
    with library.LOCK:
        try:
            previous = _read(root)
        except (OSError, ValueError, TypeError, UnicodeError):
            return {"ok": False, "status": "HOLD_PREVIOUS_PLAN_PRESERVED"}
        old = {_id(x): x for x in previous["tasks"]}
        images = {r["id"]: r for r in report.get("local_catalog", [])
                  if isinstance(r, dict) and isinstance(r.get("id"), str)}
        sources = {r["source_record_id"]: r for r in report.get("source_catalog", [])
                   if isinstance(r, dict) and isinstance(r.get("source_record_id"), str)}
        matches = report.get("catalog_matches", [])
        if not isinstance(matches, list):
            return {"ok": False, "status": "HOLD_MATCH_SCHEMA"}
        matched_images = {r.get("id") for r in matches if isinstance(r, dict)
                          and r.get("match") == "CODE_MATCH"}
        matched_sources = {r.get("source_record_id") for r in matches if isinstance(r, dict)
                           and r.get("match") == "CODE_MATCH"}
        seen = set()
        tasks = []
        for task in report["gap_queue"]:
            ident = _id(task)
            if not ident or ident in seen:
                return {"ok": False, "status": "HOLD_GAP_IDENTITY"}
            seen.add(ident)
            older = old.get(ident, {})
            action = _action(task, images, sources)
            item = {k: task.get(k) for k in
                    ("direction", "image_id", "source_record_id", "game_id",
                     "region", "kind", "name", "reason") if k in task}
            item.update(recheck_action=action,
                        status="AUTOMATIC_RECHECK_ELIGIBLE" if action in (
                            "EXISTING_PROVIDER_METADATA_RETRY",
                            "PRIORITIZE_APPROVED_PROVIDER_COVERAGE") else "REVIEW_REQUIRED",
                        first_seen_at=older.get("first_seen_at", stamp),
                        last_seen_at=stamp,
                        observed_cycles=min(1000000, max(0, older.get("observed_cycles", 0)) + 1)
                        if type(older.get("observed_cycles", 0)) is int else 1)
            tasks.append(item)
        # Missing gap != solved gap. Only exact checked matches permit "verified".
        history = []
        for ident, old_item in old.items():
            if ident in seen:
                continue
            matched = (old_item["direction"] == "IMAGE_NEEDS_METADATA"
                       and old_item.get("image_id") in matched_images
                       or old_item["direction"] == "CATALOG_NEEDS_IMAGE"
                       and old_item.get("source_record_id") in matched_sources)
            prior = dict(old_item)
            prior["status"] = "VERIFIED_EXACT_MATCH" if matched else "NO_LONGER_OBSERVED"
            prior["last_checked_at"] = stamp
            history.append(prior)
        for row in previous["history"]:
            if _id(row) not in old and _id(row) not in seen:
                history.append(row)
        history = history[:MAX_HISTORY]
        payload = {"schema": SCHEMA, "updated_at": stamp,
                   "physical_tablet_verified": False, "auto_promoted": False,
                   "source_index_or_images_changed": False,
                   "tasks": tasks, "history": history,
                   "summary": {"active": len(tasks),
                               "automatically_recheckable": sum(
                                   x["status"] == "AUTOMATIC_RECHECK_ELIGIBLE" for x in tasks),
                               "review_required": sum(x["status"] == "REVIEW_REQUIRED" for x in tasks),
                               "verified_exact_matches": sum(
                                   x["status"] == "VERIFIED_EXACT_MATCH" for x in history),
                               "no_longer_observed": sum(
                                   x["status"] == "NO_LONGER_OBSERVED" for x in history),
                               "actions": dict(Counter(x["recheck_action"] for x in tasks))}}
        destination = root / FILENAME
        if destination.is_symlink():
            return {"ok": False, "status": "HOLD_PREVIOUS_PLAN_PRESERVED"}
        data = (json.dumps(payload, ensure_ascii=False,
                           separators=(",", ":")) + "\n").encode("utf-8")
        if len(data) > MAX_BYTES:
            return {"ok": False, "status": "HOLD_PLAN_SIZE"}
        library._atomic_write(destination, data)
        return {"ok": True, "status": "PRIVATE_RECIPROCAL_PLAN_UPDATED",
                "summary": payload["summary"]}


def read_summary(*, root=None):
    """Read-only, aggregate-only view for the existing localhost catalog API."""
    try:
        root = Path(root) if root is not None else library.storage_root()
        if not (root / FILENAME).exists():
            return {"status": "NOT_RUN", "physical_tablet_verified": False}
        with library.LOCK:
            plan = _read(root)
        tasks = plan["tasks"]
        history = plan["history"]
        summary = {"active": len(tasks),
                   "automatically_recheckable": sum(
                       t.get("status") == "AUTOMATIC_RECHECK_ELIGIBLE" for t in tasks),
                   "review_required": sum(
                       t.get("status") == "REVIEW_REQUIRED" for t in tasks),
                   "verified_exact_matches": sum(
                       t.get("status") == "VERIFIED_EXACT_MATCH" for t in history),
                   "no_longer_observed": sum(
                       t.get("status") == "NO_LONGER_OBSERVED" for t in history)}
        return {"status": "PRIVATE_RECHECK_PLAN_AVAILABLE", "summary": summary,
                "physical_tablet_verified": False}
    except (OSError, ValueError, TypeError, UnicodeError):
        return {"status": "HOLD_PLAN_UNREADABLE", "physical_tablet_verified": False}

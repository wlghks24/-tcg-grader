#!/usr/bin/env python3
"""V653: collect local operational receipts; NEVER certify neural outcomes.

Requires fresh successful market collection report and two matching outputs.
Writes only bounded device-local observations, not V373/V375 learning stores.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from safe_runtime import atomic_write_json

FILES = ("market_prices.json", "market_watch.json")
NAME = "collector_observations_v653.json"
MAX_BYTES = 2_000_000
MAX_ROWS = 64

class Hold(ValueError):
    pass

def _stamp(v):
    if not isinstance(v, str) or len(v) > 64:
        raise Hold("BAD_TIME")
    try:
        d = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError as e:
        raise Hold("BAD_TIME") from e
    if d.tzinfo is None:
        raise Hold("NAIVE_TIME")
    return d.astimezone(timezone.utc)

def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise Hold("DUPLICATE_JSON_KEY")
        out[key] = value
    return out

def _load(path):
    if path.is_symlink() or not path.is_file():
        raise Hold("MISSING_OR_UNSAFE_" + path.name)
    try:
        if path.stat().st_size > MAX_BYTES:
            raise Hold("OVERSIZE_" + path.name)
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(Hold("NONFINITE")))
    except (OSError, UnicodeError, TypeError, ValueError) as e:
        if isinstance(e, Hold):
            raise
        raise Hold("UNREADABLE_" + path.name) from e
    if not isinstance(value, dict):
        raise Hold("BAD_OBJECT_" + path.name)
    return value, hashlib.sha256(raw).hexdigest()

def observe(root, now=None):
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if root.is_symlink() or not root.is_dir():
        raise Hold("UNSAFE_ROOT")
    report, digest = _load(root / "auto_update_report.json")
    start, end = _stamp(report.get("started_at")), _stamp(report.get("finished_at"))
    if start > end or end > now + timedelta(minutes=5) or now - end > timedelta(hours=36):
        raise Hold("STALE_OR_UNORDERED_REPORT")
    if report.get("ok") is not True or not isinstance(report.get("trigger"), str) or not report["trigger"]:
        raise Hold("COLLECTOR_NOT_OK")
    if any(type(report.get(k)) is not int or report[k] != 0
           for k in ("failure_count", "degraded_count", "fresh_failure_count")):
        raise Hold("COLLECTOR_DEGRADED")
    rows = report.get("results")
    if not isinstance(rows, list) or not (2 <= len(rows) <= 64):
        raise Hold("BAD_JOB_LIST")
    postflight = report.get("postflight_monitor")
    if (not isinstance(postflight, dict) or postflight.get("ok") is not True
            or not isinstance(postflight.get("results"), list)
            or not (2 <= len(postflight["results"]) <= 64)):
        raise Hold("POSTFLIGHT_NOT_VERIFIED")
    postflight_files = {}
    for pf in postflight["results"]:
        if not isinstance(pf, dict) or not isinstance(pf.get("file"), str):
            raise Hold("BAD_POSTFLIGHT_ROW")
        if pf["file"] in postflight_files:
            raise Hold("DUPLICATE_POSTFLIGHT_ROW")
        postflight_files[pf["file"]] = pf
    by_file = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("file"), str):
            raise Hold("BAD_JOB")
        if row["file"] in by_file:
            raise Hold("DUPLICATE_JOB")
        by_file[row["file"]] = row
    hashes = {}
    for name in FILES:
        job = by_file.get(name)
        pf = postflight_files.get(name)
        if not isinstance(pf, dict) or pf.get("ok") is not True:
            raise Hold("POSTFLIGHT_FILE_NOT_VERIFIED_" + name)
        if not isinstance(job, dict) or job.get("ok") is not True:
            raise Hold("JOB_FAILED_" + name)
        if job.get("collection_errors") or job.get("remaining_collection_errors"):
            raise Hold("JOB_ERRORS_" + name)
        job_end = _stamp(job.get("updated_at"))
        payload, output_digest = _load(root / name)
        if not isinstance(payload.get("collection_errors"), list) or payload["collection_errors"]:
            raise Hold("OUTPUT_SOURCE_ERRORS_" + name)
        if payload.get("collection_status") != "정상":
            raise Hold("OUTPUT_NOT_HEALTHY_" + name)
        output_end = _stamp(payload.get("updated_at"))
        if (not start - timedelta(minutes=5) <= job_end <= end + timedelta(minutes=5)
                or not start - timedelta(minutes=5) <= output_end <= end + timedelta(minutes=5)
                or abs((output_end - job_end).total_seconds()) > 600):
            raise Hold("UNMATCHED_OUTPUT_" + name)
        if name == "market_prices.json" and (
            not isinstance(payload.get("entries"), dict) or not payload["entries"]
        ):
            raise Hold("EMPTY_MARKET")
        if name == "market_watch.json" and not isinstance(payload.get("items"), list):
            raise Hold("BAD_WATCH")
        hashes[name] = output_digest
    return {
        "schema_version": 1, "finished_at": end.isoformat(timespec="seconds"),
        "trigger": report["trigger"][:80], "report_sha256": digest,
        "output_sha256": hashes, "observation_only": True,
        "external_source_truth_verified": False,
        "verified_neural_outcome": False, "training_enabled": False,
    }

def capture(root, state_dir, now=None):
    try:
        record = observe(root, now=now)
    except Hold as e:
        return {"status": "EVIDENCE_HOLD", "reason": str(e), "written": False}
    if state_dir.is_symlink() or not state_dir.is_dir():
        return {"status": "EVIDENCE_HOLD", "reason": "UNSAFE_STATE_DIR", "written": False}
    lock = state_dir / ".v653.lock"
    if lock.is_symlink():
        return {"status": "EVIDENCE_HOLD", "reason": "UNSAFE_LOCK", "written": False}
    try:
        fd = os.open(lock, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    except OSError:
        return {"status": "EVIDENCE_HOLD", "reason": "LOCK_ERROR", "written": False}
    with os.fdopen(fd, "r+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return {"status": "EVIDENCE_HOLD", "reason": "BUSY", "written": False}
        path = state_dir / NAME
        if path.is_symlink():
            return {"status": "EVIDENCE_HOLD", "reason": "STATE_SYMLINK", "written": False}
        old = []
        if path.exists():
            try:
                value, _ = _load(path)
                if value.get("schema_version") != 1 or not isinstance(value.get("observations"), list):
                    raise Hold("STATE_SCHEMA")
                old = value["observations"]
                if len(old) > MAX_ROWS or any(
                    not isinstance(r, dict) or r.get("verified_neural_outcome") is not False
                    for r in old
                ):
                    raise Hold("STATE_CONTENT")
            except Hold as e:
                return {"status": "EVIDENCE_HOLD", "reason": str(e), "written": False}
        if any(x.get("report_sha256") == record["report_sha256"] for x in old):
            return {"status": "ALREADY_OBSERVED", "written": False, "count": len(old)}
        if old and record["finished_at"] <= str(old[-1].get("finished_at") or ""):
            return {"status": "EVIDENCE_HOLD", "reason": "REPLAY_OR_TIME_REVERSAL", "written": False}
        merged = (old + [record])[-MAX_ROWS:]
        try:
            atomic_write_json(path, {"schema_version": 1, "observations": merged},
                              suffix=".v653-observation.tmp")
        except (OSError, TypeError, ValueError):
            return {"status": "EVIDENCE_HOLD", "reason": "WRITE_FAILED", "written": False}
        return {"status": "OBSERVATION_RECORDED_NOT_VERIFIED", "written": True,
                "count": len(merged), "v387_confidence_unchanged": True}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--state-dir", type=Path, required=True)
    args = p.parse_args()
    print("V653_RECEIPT=" + json.dumps(capture(args.root, args.state_dir), sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

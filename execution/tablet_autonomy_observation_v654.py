#!/usr/bin/env python3
"""V654: passive real-collector observation evidence, never verified training.

Runs after the existing daily V400 cycle even when that cycle returns HOLD.
No collector is started here, no V374/V375 stores are modified, and a locally
observed change must NEVER be represented as a verified causal reward.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

MAX_SOURCE_BYTES = 4_000_000
MAX_STATE_BYTES = 1_000_000
MAX_OBSERVATIONS = 96
MAX_SOURCE_AGE_HOURS = 72
REQUIRED_RESULTS = frozenset({
    "releases.json", "market_prices.json", "market_watch.json",
    "promo_events.json", "purchase_sources.json",
    "exchange_rates.json", "grading_company_updates.json",
})


def _read(path: Path, limit: int) -> tuple[dict[str, Any] | None, str | None]:
    if path.is_symlink():
        return None, "SYMLINK_HOLD"
    try:
        if not path.is_file() or path.stat().st_size > limit:
            return None, "MISSING_OR_OVERSIZE_HOLD"
        raw = path.read_bytes()
        if len(raw) > limit:
            return None, "OVERSIZE_HOLD"
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            return None, "NOT_OBJECT_HOLD"
        return data, hashlib.sha256(raw).hexdigest()
    except (OSError, UnicodeError, ValueError, TypeError):
        return None, "INVALID_JSON_HOLD"


def _time(value: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if d.tzinfo is None:
            return None
        return d.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def inspect(root: Path, *, now: datetime | None = None) -> dict[str, Any]:
    moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    data, data_sha = _read(root / "tcg_live_data.json", MAX_SOURCE_BYTES)
    report, report_sha = _read(root / "auto_update_report.json", MAX_SOURCE_BYTES)
    if data is None or report is None:
        return {"status": "SOURCE_EVIDENCE_HOLD", "reason": "MISSING_OR_INVALID_SOURCE_FILE",
                "db_usable": data is not None, "report_usable": report is not None,
                "verified_training_samples_added": 0}
    meta = data.get("auto_update")
    if not isinstance(meta, dict) or meta.get("report_ok") is not True or meta.get("full_update") is not True:
        return {"status": "SOURCE_EVIDENCE_HOLD", "reason": "NO_SUCCESSFUL_COLLECTOR_RUN",
                "verified_training_samples_added": 0}
    started = _time(meta.get("last_run"))
    if started is None or started > moment + timedelta(minutes=15) or started < moment - timedelta(hours=MAX_SOURCE_AGE_HOURS):
        return {"status": "SOURCE_EVIDENCE_HOLD", "reason": "STALE_OR_INVALID_RUN_TIME",
                "verified_training_samples_added": 0}
    rows = report.get("results")
    if not isinstance(rows, list) or len(rows) > 128:
        return {"status": "SOURCE_EVIDENCE_HOLD", "reason": "INVALID_RESULTS",
                "verified_training_samples_added": 0}
    by_name = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("file"), str):
            path = row["file"]
            if path in by_name:
                return {"status": "SOURCE_EVIDENCE_HOLD", "reason": "DUPLICATE_RESULT",
                        "verified_training_samples_added": 0}
            by_name[path] = row
    if not REQUIRED_RESULTS.issubset(by_name):
        return {"status": "SOURCE_EVIDENCE_HOLD", "reason": "INCOMPLETE_RESULT_FILES",
                "verified_training_samples_added": 0}
    # This is an observation of report claims, not an independent source verification.
    source_ok = (
        report.get("ok") is True or report.get("ok_with_aux") is True
        or report.get("ok_with_monitor") is True
    )
    if not source_ok:
        return {"status": "SOURCE_EVIDENCE_HOLD", "reason": "COLLECTOR_REPORTED_FAILURE",
                "verified_training_samples_added": 0}
    record = {
        "schema_version": 1,
        "kind": "local_collector_observation_only",
        "observed_at": moment.isoformat(timespec="seconds"),
        "collector_run_at": started.isoformat(timespec="seconds"),
        "collector_trigger": str(meta.get("trigger") or "unknown")[:72],
        "report_ok": True,
        "source_error_count": max(0, min(99999, int(meta.get("source_error_count") or 0)))
        if str(meta.get("source_error_count") or "0").isdigit() else None,
        "data_sha256": data_sha,
        "report_sha256": report_sha,
        "observed_files": sorted(REQUIRED_RESULTS),
        "verified": False,
        "causal_proof": False,
        "confidence_eligible": False,
        "training_reward": None,
    }
    # Date+content binding is safe for dedup, not cryptographic source authentication.
    record["observation_id"] = hashlib.sha256(
        (record["collector_run_at"] + "|" + data_sha + "|" + report_sha).encode("utf-8")
    ).hexdigest()
    return {"status": "PASSIVE_OBSERVATION_READY", "observation": record,
            "verified_training_samples_added": 0,
            "independent_execution_proven": False}


def _store(path: Path, entry: dict[str, Any]) -> dict[str, Any]:
    if path.is_symlink():
        return {"status": "UNSAFE_STATE_PATH_HOLD", "written": False}
    rows: list[dict[str, Any]] = []
    if path.exists():
        old, error = _read(path, MAX_STATE_BYTES)
        if old is None or old.get("schema_version") != 1 or not isinstance(old.get("observations"), list):
            return {"status": "CORRUPT_STATE_HOLD", "written": False, "error": error}
        rows = old["observations"]
        if len(rows) > MAX_OBSERVATIONS or any(
            not isinstance(item, dict) or item.get("kind") != "local_collector_observation_only"
            or item.get("verified") is not False or item.get("confidence_eligible") is not False
            for item in rows
        ):
            return {"status": "CORRUPT_STATE_HOLD", "written": False}
        if any(row.get("observation_id") == entry["observation_id"] for row in rows):
            return {"status": "ALREADY_OBSERVED", "written": False, "count": len(rows)}
    rows = (rows + [entry])[-MAX_OBSERVATIONS:]
    payload = (json.dumps({"schema_version": 1, "observations": rows},
                          ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    if len(payload) > MAX_STATE_BYTES:
        return {"status": "STATE_SIZE_HOLD", "written": False}
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.parent.is_symlink():
            return {"status": "UNSAFE_PARENT_HOLD", "written": False}
        tmp = path.parent / (path.name + ".tmp." + str(os.getpid()))
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                tmp.unlink()
    except (OSError, ValueError, TypeError):
        return {"status": "STATE_WRITE_HOLD", "written": False}
    return {"status": "OBSERVATION_SAVED_NOT_VERIFIED", "written": True,
            "count": len(rows), "verified_training_samples_added": 0}


def cycle(root: Path, state_path: Path, *, capture: bool = False,
          now: datetime | None = None) -> dict[str, Any]:
    result = inspect(root, now=now)
    if result["status"] != "PASSIVE_OBSERVATION_READY" or not capture:
        return result
    stored = _store(state_path, result["observation"])
    return {"status": stored["status"], "storage": stored,
            "observation_id": result["observation"]["observation_id"],
            "verified_training_samples_added": 0, "independent_execution_proven": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--capture", action="store_true")
    args = parser.parse_args()
    result = cycle(args.root, args.state, capture=args.capture)
    print("V654_EVIDENCE=" + json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in {"OBSERVATION_SAVED_NOT_VERIFIED",
                                     "PASSIVE_OBSERVATION_READY", "ALREADY_OBSERVED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

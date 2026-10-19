#!/usr/bin/env python3
"""V654: append-only-in-meaning observations of ACTUAL scheduled autonomy logs.

A runtime log checksum is NOT a causal learning outcome, model-training row,
authenticated source receipt, or independent proof of market/card facts.
No writes to V373/V374/V375 stores, Git, models, prices, grades or source files.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OUTPUT_NAME = "autonomy-observations-v654.json"
SCHEMA_VERSION = 1
MAX_LOG_BYTES = 8_000_000
MAX_JOURNAL_BYTES = 1_000_000
MAX_RECORDS = 180
MAX_LOG_RECORDS = 20
HEX_SHA = re.compile(r"^[0-9a-f]{40}$")
LOG_NAME = re.compile(r"^autonomy-[0-9]{8}-[0-9]{6}\.log$")
ZERO = "0" * 64


class EvidenceHold(ValueError):
    pass


def _digest(item: Any) -> str:
    data = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _empty() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "total_observations": 0,
            "anchor_sha256": ZERO, "observations": []}


def _load(state_dir: Path) -> dict[str, Any]:
    path = state_dir / OUTPUT_NAME
    if path.is_symlink():
        raise EvidenceHold("JOURNAL_SYMLINK_HOLD")
    if not path.exists():
        return _empty()
    try:
        if not path.is_file() or path.stat().st_size > MAX_JOURNAL_BYTES:
            raise EvidenceHold("JOURNAL_SIZE_HOLD")
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError, TypeError) as exc:
        raise EvidenceHold("JOURNAL_CORRUPTION_HOLD") from exc
    if not isinstance(data, dict) or set(data) != {
        "schema_version", "total_observations", "anchor_sha256", "observations"
    } or data["schema_version"] != SCHEMA_VERSION:
        raise EvidenceHold("JOURNAL_SCHEMA_HOLD")
    rows = data["observations"]
    if not isinstance(rows, list) or len(rows) > MAX_RECORDS:
        raise EvidenceHold("JOURNAL_ROWS_HOLD")
    n = data["total_observations"]
    if type(n) is not int or n < len(rows) or n < 0:
        raise EvidenceHold("JOURNAL_COUNT_HOLD")
    prev = data["anchor_sha256"]
    if not isinstance(prev, str) or not re.fullmatch("[0-9a-f]{64}", prev):
        raise EvidenceHold("JOURNAL_ANCHOR_HOLD")
    keys = set()
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("receipt_sha256"), str):
            raise EvidenceHold("JOURNAL_ROW_HOLD")
        payload = {k: v for k, v in row.items() if k != "receipt_sha256"}
        if row.get("previous_receipt_sha256") != prev or _digest(payload) != row["receipt_sha256"]:
            raise EvidenceHold("JOURNAL_CHAIN_HOLD")
        if (row.get("kind") != "UNVERIFIED_RUNTIME_OBSERVATION"
                or row.get("eligible_for_training") is not False
                or row.get("verified") is not False):
            raise EvidenceHold("JOURNAL_TRUST_HOLD")
        correlation = row.get("collector_correlation")
        if correlation is not None:
            if (not isinstance(correlation, dict)
                    or any(correlation.get(field) is not False for field in (
                        "independent_source_attestation", "causal_action_proven",
                        "eligible_for_training", "verified"
                    ))):
                raise EvidenceHold("JOURNAL_NESTED_TRUST_HOLD")
            accepted_statuses = {
                "COLLECTOR_NOT_CONFIGURED", "COLLECTOR_UNSAFE_PATH",
                "COLLECTOR_OBSERVATION_MISSING", "COLLECTOR_OBSERVATION_STALE",
                "COLLECTOR_OUTPUT_MISMATCH", "COLLECTOR_CORRELATION_HOLD",
                "LOCAL_COLLECTOR_CORRELATED_UNVERIFIED",
            }
            if correlation.get("status") not in accepted_statuses:
                raise EvidenceHold("JOURNAL_CORRELATION_STATUS_HOLD")
            if correlation.get("status") == "LOCAL_COLLECTOR_CORRELATED_UNVERIFIED":
                digest = correlation.get("report_sha256")
                output = correlation.get("output_sha256")
                if (not isinstance(digest, str)
                        or not re.fullmatch(r"[0-9a-f]{64}", digest)
                        or not isinstance(output, dict)
                        or set(output) != {"market_prices.json", "market_watch.json"}
                        or any(not isinstance(v, str)
                               or not re.fullmatch(r"[0-9a-f]{64}", v)
                               for v in output.values())):
                    raise EvidenceHold("JOURNAL_CORRELATION_DIGEST_HOLD")
        key = row.get("run_id")
        if not isinstance(key, str) or key in keys:
            raise EvidenceHold("JOURNAL_DUPLICATE_HOLD")
        keys.add(key)
        prev = row["receipt_sha256"]
    return data


def _parse_report(raw: bytes) -> dict[str, Any]:
    try:
        lines = raw.decode("utf-8", errors="replace").splitlines()
    except (ValueError, TypeError):
        return {}
    for line in reversed(lines[-MAX_LOG_RECORDS:]):
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict) and "v400_status" in obj:
            return obj
    return {}


def _safe_log(state_dir: Path, path: Path) -> bytes:
    if (path.parent != state_dir / "logs" or not LOG_NAME.fullmatch(path.name)
            or path.is_symlink()):
        raise EvidenceHold("UNSAFE_LOG_PATH_HOLD")
    try:
        if not path.is_file() or path.stat().st_size > MAX_LOG_BYTES:
            raise EvidenceHold("LOG_SIZE_HOLD")
        return path.read_bytes()
    except OSError as exc:
        raise EvidenceHold("LOG_UNREADABLE_HOLD") from exc


def _collector_correlation(state_dir: Path, root: Path | None) -> dict[str, Any]:
    """Cross-check V653 receipts with current local bytes, without trust promotion.

    The state and source reports share a device trust boundary. A match is NOT
    independent proof of a causal action or external market/source truth.
    """
    result = {
        "status": "COLLECTOR_NOT_CONFIGURED",
        "independent_source_attestation": False,
        "causal_action_proven": False,
        "eligible_for_training": False,
        "verified": False,
    }
    if root is None:
        return result
    from execution import tablet_autonomy_collection_receipts_v653 as v653
    observation_dir = state_dir / "collection-evidence-v653"
    path = observation_dir / v653.NAME
    if (root.is_symlink() or not root.is_dir()
            or observation_dir.is_symlink() or not observation_dir.is_dir()
            or path.is_symlink()):
        return {**result, "status": "COLLECTOR_UNSAFE_PATH"}
    if not path.exists():
        return {**result, "status": "COLLECTOR_OBSERVATION_MISSING"}
    try:
        content, _ = v653._load(path)
        if content.get("schema_version") != 1:
            raise v653.Hold("BAD_STATE_SCHEMA")
        records = content.get("observations")
        if not isinstance(records, list) or not (1 <= len(records) <= v653.MAX_ROWS):
            raise v653.Hold("BAD_STATE_ROWS")
        latest = records[-1]
        if (not isinstance(latest, dict)
                or latest.get("observation_only") is not True
                or latest.get("external_source_truth_verified") is not False
                or latest.get("verified_neural_outcome") is not False
                or latest.get("training_enabled") is not False
                or not isinstance(latest.get("output_sha256"), dict)):
            raise v653.Hold("UNTRUSTED_OBSERVATION")
        # Re-evaluate the original exact input files, not merely the saved
        # report's self-reported success flags.
        now = datetime.now(timezone.utc)
        current = v653.observe(root, now=now)
        finished = datetime.fromisoformat(str(latest["finished_at"]).replace("Z", "+00:00"))
        if (finished.tzinfo is None or (now - finished.astimezone(timezone.utc)).total_seconds() > 10800
                or (finished.astimezone(timezone.utc) - now).total_seconds() > 300):
            return {**result, "status": "COLLECTOR_OBSERVATION_STALE"}
        if (current["report_sha256"] != latest.get("report_sha256")
                or current["output_sha256"] != latest["output_sha256"]
                or current["finished_at"] != latest.get("finished_at")):
            return {**result, "status": "COLLECTOR_OUTPUT_MISMATCH"}
        return {
            **result,
            "status": "LOCAL_COLLECTOR_CORRELATED_UNVERIFIED",
            "report_sha256": current["report_sha256"],
            "output_sha256": current["output_sha256"],
            "finished_at": current["finished_at"],
            "independent_source_attestation": False,
            "causal_action_proven": False,
            "eligible_for_training": False,
            "verified": False,
        }
    except (v653.Hold, OSError, ValueError, TypeError, KeyError, UnicodeError):
        return {**result, "status": "COLLECTOR_CORRELATION_HOLD"}


def _receipt(log: Path, raw: bytes, head_sha: str, autonomy_result: str, *,
             state_dir: Path, root: Path | None = None) -> dict[str, Any]:
    report = _parse_report(raw)
    p = report.get("v387_uncertainty_policy") or {}
    p = p if isinstance(p, dict) else {}
    g = report.get("v387_autonomous_gate") or {}
    g = g if isinstance(g, dict) else {}
    execution = report.get("execution") or {}
    execution = execution if isinstance(execution, dict) else {}
    return {
        "kind": "UNVERIFIED_RUNTIME_OBSERVATION",
        "verified": False,
        "eligible_for_training": False,
        "provenance": "LOCAL_LOG_CHECKSUM_ONLY_NOT_INDEPENDENTLY_ATTESTED",
        "run_id": hashlib.sha256((head_sha + "|" + log.name).encode("utf-8")).hexdigest(),
        "local_main_sha": head_sha,
        "log_basename": log.name,
        "log_sha256": hashlib.sha256(raw).hexdigest(),
        "log_bytes": len(raw),
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "autonomy_result": autonomy_result[:80],
        "v400_status": str(report.get("v400_status") or "NO_STRUCTURED_V400")[:80],
        "v387_gate": str(g.get("status") or "UNAVAILABLE")[:80],
        "selected_action": str(p.get("selected_action") or "NONE")[:80],
        "reported_confidence": p.get("selected_confidence") if isinstance(p.get("selected_confidence"), (int, float)) else None,
        "executed_as_reported": execution.get("executed") is True,
        "causal_improvement_proven": False,
        "collector_correlation": _collector_correlation(state_dir, root),
    }


def _atomic_save(state_dir: Path, data: dict[str, Any]) -> None:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    if len(raw.encode("utf-8")) > MAX_JOURNAL_BYTES:
        raise EvidenceHold("JOURNAL_CAPACITY_HOLD")
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         prefix=".v654-", suffix=".tmp",
                                         dir=state_dir, delete=False) as f:
            temp = Path(f.name)
            os.chmod(f.name, 0o600)
            f.write(raw)
            f.flush()
            os.fsync(f.fileno())
        target = state_dir / OUTPUT_NAME
        if target.is_symlink():
            raise EvidenceHold("JOURNAL_SYMLINK_HOLD")
        os.replace(temp, target)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def record(state_dir: Path, log: Path, head_sha: str, autonomy_result: str,
           *, root: Path | None = None) -> dict[str, Any]:
    if not HEX_SHA.fullmatch(head_sha):
        raise EvidenceHold("INVALID_MAIN_SHA_HOLD")
    if state_dir.is_symlink() or not state_dir.is_dir():
        raise EvidenceHold("STATE_DIRECTORY_HOLD")
    raw = _safe_log(state_dir, log)
    item = _receipt(log, raw, head_sha, autonomy_result, state_dir=state_dir, root=root)
    lock_path = state_dir / ".autonomy-observations-v654.lock"
    if lock_path.is_symlink():
        raise EvidenceHold("LOCK_SYMLINK_HOLD")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        data = _load(state_dir)
        for row in data["observations"]:
            if row["run_id"] == item["run_id"]:
                if row["log_sha256"] != item["log_sha256"]:
                    raise EvidenceHold("SOURCE_LOG_CHANGED_HOLD")
                return {"status": "ALREADY_RECORDED", "observation_total": data["total_observations"],
                        "eligible_for_training": False}
        prev = data["observations"][-1]["receipt_sha256"] if data["observations"] else data["anchor_sha256"]
        item["previous_receipt_sha256"] = prev
        item["receipt_sha256"] = _digest(item)
        rows = data["observations"] + [item]
        if len(rows) > MAX_RECORDS:
            data["anchor_sha256"] = rows[0]["receipt_sha256"]
            rows = rows[1:]
        data["observations"] = rows
        data["total_observations"] += 1
        _atomic_save(state_dir, data)
        return {"status": "OBSERVATION_RECORDED_UNVERIFIED",
                "observation_total": data["total_observations"],
                "eligible_for_training": False,
                "run_id": item["run_id"][:12]}
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def status(state_dir: Path) -> dict[str, Any]:
    if state_dir.is_symlink() or not state_dir.is_dir():
        raise EvidenceHold("STATE_DIRECTORY_HOLD")
    data = _load(state_dir)
    rows = data["observations"]
    return {"status": "OBSERVATION_ONLY_NOT_TRAINING",
            "observation_total": data["total_observations"],
            "latest_autonomy_result": rows[-1]["autonomy_result"] if rows else None,
            "last_observation_run_id": rows[-1]["run_id"][:12] if rows else None,
            "eligible_for_training": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("--log", type=Path)
    parser.add_argument("--head-sha")
    parser.add_argument("--autonomy-result", default="UNKNOWN")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()
    try:
        if args.status:
            result = status(args.state_dir)
        else:
            if args.log is None or args.head_sha is None:
                parser.error("--log and --head-sha required without --status")
            result = record(args.state_dir, args.log, args.head_sha, args.autonomy_result,
                            root=args.root)
        print("V654_AUTONOMY_EVIDENCE=" + json.dumps(result, sort_keys=True))
        return 0
    except EvidenceHold as exc:
        print("V654_AUTONOMY_EVIDENCE_HOLD=" + str(exc))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

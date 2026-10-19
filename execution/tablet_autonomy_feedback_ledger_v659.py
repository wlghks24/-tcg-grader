#!/usr/bin/env python3
"""V659: single-file transactional staging for V374/V375 feedback candidates.

SQLite provides one atomic transaction for paired candidate rows. Staged data
is NEVER a V373 outcome or independent attestation and cannot train V387.
No existing JSONL, model, grade, market fact, Git or source file is touched.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from pathlib import Path

from execution.tablet_autonomy_outcome_lineage_v657 import ACTIONS

MAX_LEDGER_BYTES = 8_000_000
MAX_PAIRS = 256


class Guarded(ValueError):
    pass


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      allow_nan=False, separators=(",", ":"))


def _check_pair(skill: dict, meta: dict) -> tuple[str, str]:
    if not isinstance(skill, dict) or not isinstance(meta, dict):
        raise Guarded("BAD_PAIR")
    ref = skill.get("evidence_ref")
    recipe = skill.get("recipe")
    reward = skill.get("reward")
    features = meta.get("features")
    if (skill.get("verified") is not True or meta.get("verified") is not True
            or not isinstance(ref, str) or len(ref) < 3 or len(ref) > 200
            or recipe not in ACTIONS or meta.get("action_id") != ACTIONS[recipe]
            or meta.get("evidence_ref") != "v375:" + ref
            or isinstance(reward, bool) or not isinstance(reward, (int, float))
            or not math.isfinite(reward) or not -1.0 <= reward <= 1.0
            or isinstance(meta.get("reward"), bool)
            or not isinstance(meta.get("reward"), (int, float))
            or not math.isfinite(meta["reward"])
            or abs(meta["reward"] - reward) > 1e-6
            or not isinstance(features, list) or len(features) != 10
            or any(isinstance(x, bool) or not isinstance(x, (int, float))
                   or not math.isfinite(x) or not 0 <= x <= 1 for x in features)):
        raise Guarded("EVIDENCE_SCHEMA_OR_CAUSAL_MAPPING_HOLD")
    payload = _json({"skill": skill, "meta": meta})
    return ref, hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_db(path: Path) -> None:
    if path.is_symlink() or path.parent.is_symlink():
        raise Guarded("UNSAFE_SYMLINK")
    if not path.parent.is_dir():
        raise Guarded("MISSING_PARENT")
    if path.exists() and (not path.is_file() or path.stat().st_size > MAX_LEDGER_BYTES):
        raise Guarded("UNSAFE_OR_OVERSIZE_LEDGER")


def stage_pairs(db: Path, pairs: list[tuple[dict, dict]]) -> dict:
    """Stage bounded pairs atomically; NEVER promote trust or edit JSONL.

    This API requires caller-supplied real evidence and cannot certify it.
    It is intentionally not accessible as a production CLI write action.
    """
    _safe_db(db)
    if not isinstance(pairs, list) or not 1 <= len(pairs) <= MAX_PAIRS:
        raise Guarded("INVALID_PAIR_BATCH")
    validated = [(_check_pair(a, b), a, b) for a, b in pairs]
    references = [x[0][0] for x in validated]
    if len(set(references)) != len(references):
        raise Guarded("DUPLICATE_REF_IN_BATCH")
    connection = sqlite3.connect(db, timeout=2, isolation_level=None)
    try:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("CREATE TABLE IF NOT EXISTS candidate_pairs ("
                           "evidence_ref TEXT PRIMARY KEY, "
                           "sha256 TEXT NOT NULL, skill_json TEXT NOT NULL, "
                           "meta_json TEXT NOT NULL, "
                           "status TEXT NOT NULL CHECK(status='UNATTESTED'))")
        connection.execute("BEGIN IMMEDIATE")
        written = 0
        for (ref, digest), skill, meta in validated:
            old = connection.execute(
                "SELECT sha256 FROM candidate_pairs WHERE evidence_ref=?", (ref,)
            ).fetchone()
            if old:
                if old[0] != digest:
                    raise Guarded("CONFLICTING_REPLAY_HOLD")
                continue
            connection.execute(
                "INSERT INTO candidate_pairs VALUES (?,?,?,?,?)",
                (ref, digest, _json(skill), _json(meta), "UNATTESTED")
            )
            written += 1
        connection.execute("COMMIT")
        return {"status": "STAGED_UNATTESTED", "staged": written,
                "training_authorized": False, "v387_confidence_changed": False}
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()


def audit(db: Path) -> dict:
    if db.is_symlink() or db.parent.is_symlink():
        return {"status": "UNSAFE_LEDGER_HOLD", "training_authorized": False}
    if not db.is_file():
        return {"status": "NO_LEDGER", "count": 0, "training_authorized": False}
    try:
        if db.stat().st_size > MAX_LEDGER_BYTES:
            raise Guarded("OVERSIZE")
        connection = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=2)
        try:
            rows = connection.execute(
                "SELECT evidence_ref,sha256,skill_json,meta_json,status "
                "FROM candidate_pairs ORDER BY evidence_ref"
            ).fetchall()
        finally:
            connection.close()
        if len(rows) > MAX_PAIRS:
            raise Guarded("ROW_COUNT")
        for ref, digest, a, b, status in rows:
            if status != "UNATTESTED":
                raise Guarded("ILLEGAL_PROMOTION")
            s, m = json.loads(a), json.loads(b)
            matched, expected = _check_pair(s, m)
            if ref != matched or digest != expected:
                raise Guarded("TAMPERED_PAIR")
        return {"status": "STAGED_UNATTESTED", "count": len(rows),
                "training_authorized": False, "independent_attestation": False}
    except (sqlite3.Error, Guarded, OSError, UnicodeError, ValueError):
        return {"status": "LEDGER_INTEGRITY_HOLD", "training_authorized": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args()
    print("V659_LEDGER_AUDIT=" + _json(audit(args.ledger)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

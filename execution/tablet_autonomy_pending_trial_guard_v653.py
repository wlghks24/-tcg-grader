#!/usr/bin/env python3
"""V653: fail-closed guard against unattested V374/V375 pending trials.

This module does not attest to executions or produce verified learning rows.
It only prevents deferred observations without an independent action receipt
from being later promoted as causal outcomes by the legacy evaluation path.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SKILL_STATE = "tablet_autonomy_skills_v374.json"
MAX_STATE_BYTES = 1_000_000
MAX_PENDING_TRIALS = 8
MAX_ACTIVE_SKILLS = 16


def inspect(root: Path) -> dict[str, Any]:
    path = root / SKILL_STATE
    if path.is_symlink():
        return _hold("UNSAFE_SYMLINK")
    try:
        if not path.exists():
            return {"status": "NO_PENDING_TRIALS", "allow_autonomy": True,
                    "pending_count": 0, "verified_outcomes_created": 0}
        if not path.is_file() or path.stat().st_size > MAX_STATE_BYTES:
            return _hold("UNSAFE_OR_OVERSIZE")
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError, TypeError):
        return _hold("INVALID_OR_UNREADABLE")
    if (not isinstance(state, dict)
            or state.get("schema_version") != 4
            or state.get("controller_version") != "v374"
            or not isinstance(state.get("pending_trials"), list)
            or not isinstance(state.get("active_skills"), list)
            or not isinstance(state.get("suspended_recipes"), list)
            or len(state["pending_trials"]) > MAX_PENDING_TRIALS
            or len(state["active_skills"]) > MAX_ACTIVE_SKILLS):
        return _hold("INVALID_V374_SKILL_STATE")
    pending = state["pending_trials"]
    if pending:
        # Existing V374/V375 pending entries do not contain a cryptographically
        # or independently corroborated action-execution receipt. Even a row
        # self-claiming "verified" is not independent proof. Do not silently
        # add confidence from its TTL expiry / apparent model improvement.
        return _hold("UNATTESTED_PENDING_TRIALS", pending_count=len(pending))
    return {"status": "NO_PENDING_TRIALS", "allow_autonomy": True,
            "pending_count": 0, "verified_outcomes_created": 0}


def _hold(reason: str, *, pending_count: int = 0) -> dict[str, Any]:
    return {
        "status": "TRIAL_PROVENANCE_HOLD", "reason": reason,
        "allow_autonomy": False, "pending_count": pending_count,
        "verified_outcomes_created": 0,
        "existing_evidence_preserved": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.root)
    print("V653_TRIAL_GUARD=" + json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["allow_autonomy"] is True else 3


if __name__ == "__main__":
    raise SystemExit(main())

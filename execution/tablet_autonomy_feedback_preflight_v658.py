#!/usr/bin/env python3
"""V658: fail-closed V374/V375/V373 feedback guard, before and after V400.

A schema link does not prove that an operational action actually ran.
Prevents source-mismatched, replayed or unattested meta rows from being read by
the next scheduled V400 mutating run. Never writes or approves learning.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from execution import tablet_autonomy_outcome_lineage_v657 as lineage

ALLOWED = {"NO_VERIFIED_OUTCOME_FILES"}


def inspect(root: Path) -> dict:
    report = lineage.audit(root)
    status = report["status"]
    # Empty stores are equivalent to cold start only if both already exist
    # and are truly empty; missing one of the two stores is never accepted.
    if (status == "NO_LINKABLE_RECORDS"
            and report["v374_skill_rows"] == 0
            and report["v375_v373_meta_rows"] == 0):
        status = "NO_VERIFIED_OUTCOMES_YET"
    allowed = status in ALLOWED | {"NO_VERIFIED_OUTCOMES_YET"}
    return {
        "status": "COLD_START_SAFE_TO_EVALUATE_GATE" if allowed else "FEEDBACK_PROVENANCE_HOLD",
        "reason": status,
        "allow_v400_attempt": allowed,
        "independent_attestation_confirmed": False,
        "training_outcomes_minted": 0,
        "original_file_modifications": False,
        "v387_thresholds_unchanged": True,
        "details": {k: report[k] for k in (
            "v374_skill_rows", "v375_v373_meta_rows", "schema_linked_pairs",
            "missing_meta_pairs", "unattested_model_rows", "issues"
        )},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args.root)
    print("V658_FEEDBACK_GUARD=" + json.dumps(result, sort_keys=True, ensure_ascii=False))
    return 0 if result["allow_v400_attempt"] is True else 3


if __name__ == "__main__":
    raise SystemExit(main())

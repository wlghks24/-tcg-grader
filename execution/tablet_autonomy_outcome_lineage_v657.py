#!/usr/bin/env python3
"""V657: read-only V374 -> V375 -> V373 persisted-outcome lineage audit.

Matches original refs, action mapping and rewards, but schema matches are NOT
independent causal attestation. Never writes or authorizes training.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
from typing import Any

SKILLS = "tablet_autonomy_verified_skill_outcomes_v374.jsonl"
META = "tablet_autonomy_verified_outcomes.jsonl"
MAX_BYTES = 4_000_000
MAX_ROWS = 2000
ACTIONS = {
    "RECOVER_FRESHNESS": "REFRESH_MARKET_DATA",
    "EXPAND_REGION_COVERAGE": "EXPAND_MARKET_COVERAGE",
    "RECOVER_SOURCE_HEALTH": "RECHECK_DEGRADED_SOURCES",
}


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _load(path: Path) -> tuple[str, list[dict[str, Any]]]:
    if path.is_symlink():
        return "SYMLINK_HOLD", []
    if not path.exists():
        return "MISSING", []
    try:
        if not path.is_file() or path.stat().st_size > MAX_BYTES:
            return "UNSAFE_OR_OVERSIZE_HOLD", []
        lines = path.read_text(encoding="utf-8").splitlines()
        if len(lines) > MAX_ROWS:
            return "ROW_LIMIT_HOLD", []
        rows = []
        for line in lines:
            if not line.strip():
                return "BLANK_ROW_HOLD", []
            item = json.loads(line, object_pairs_hook=_unique,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError("NONFINITE")))
            if not isinstance(item, dict):
                return "INVALID_ROW_HOLD", []
            rows.append(item)
    except (OSError, ValueError, UnicodeError, TypeError, OverflowError):
        return "INVALID_OR_UNREADABLE_HOLD", []
    return "PARSED", rows


def _evidence(value: object) -> bool:
    return isinstance(value, str) and 3 <= len(value) <= 240 and not any(
        c in value for c in ("\x00", "\r", "\n")
    )


def _reward(value: object) -> bool:
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and -1.0 <= value <= 1.0)


def _result(status: str, skills: int, meta: int, paired: int, missing: int,
            unknown: int, issues: list[str]) -> dict[str, Any]:
    return {
        "schema_version": 1, "status": status,
        "v374_skill_rows": skills, "v375_v373_meta_rows": meta,
        "schema_linked_pairs": paired, "missing_meta_pairs": missing,
        "unattested_model_rows": unknown, "issues": sorted(set(issues)),
        "independent_causal_attestation": False,
        "verified_training_outcomes_created": 0,
        "v387_confidence_changed": False,
        "read_only": True, "training_authorized": False,
    }


def audit(root: Path) -> dict[str, Any]:
    if root.is_symlink() or not root.is_dir():
        return _result("ROOT_HOLD", 0, 0, 0, 0, 0, ["UNSAFE_ROOT"])
    skill_status, skill_rows = _load(root / SKILLS)
    meta_status, meta_rows = _load(root / META)
    if skill_status.endswith("HOLD") or meta_status.endswith("HOLD"):
        return _result("CORRUPTION_HOLD", len(skill_rows), len(meta_rows), 0, 0, 0,
                       ["SKILLS:" + skill_status, "META:" + meta_status])
    if skill_status == "MISSING" and meta_status == "MISSING":
        return _result("NO_VERIFIED_OUTCOME_FILES", 0, 0, 0, 0, 0,
                       ["COLD_START_NO_SKILL_OR_META"])
    if skill_status == "MISSING" or meta_status == "MISSING":
        return _result("PARTIAL_FEED_HOLD", len(skill_rows), len(meta_rows), 0, 0, 0,
                       ["SKILLS:" + skill_status, "META:" + meta_status])
    skill_map: dict[str, dict[str, Any]] = {}
    issues = []
    for row in skill_rows:
        ref, reward = row.get("evidence_ref"), row.get("reward")
        if (row.get("verified") is not True or not _evidence(ref)
                or not isinstance(row.get("recipe"), str) or not _reward(reward)):
            issues.append("INVALID_SKILL_SCHEMA")
            continue
        if ref in skill_map:
            issues.append("DUPLICATE_SKILL_EVIDENCE")
            continue
        skill_map[ref] = row
    paired = 0
    meta_seen = set()
    matched = set()
    model_unknown = 0
    for row in meta_rows:
        ref, reward, features = row.get("evidence_ref"), row.get("reward"), row.get("features")
        if (row.get("verified") is not True or not _evidence(ref)
                or not _reward(reward)
                or not isinstance(features, list) or len(features) != 10
                or any(isinstance(x, bool) or not isinstance(x, (int, float))
                       or not math.isfinite(x) or x < 0 or x > 1 for x in features)):
            issues.append("INVALID_META_SCHEMA")
            continue
        # Non-V375 meta origins are out of this audit's scope, not corruption.
        if not ref.startswith("v375:"):
            continue
        if ref in meta_seen:
            issues.append("DUPLICATE_META_EVIDENCE")
            continue
        meta_seen.add(ref)
        original = ref[5:]
        skill = skill_map.get(original)
        if skill is None:
            issues.append("ORPHAN_META_OUTCOME")
            continue
        expected = ACTIONS.get(skill["recipe"])
        if expected is None:
            model_unknown += 1
            issues.append("UNATTESTED_OR_UNKNOWN_ACTION_MAPPING")
            continue
        if row.get("action_id") != expected or abs(float(reward) - float(skill["reward"])) > 1e-6:
            issues.append("ACTION_OR_REWARD_MISMATCH")
            continue
        if original in matched:
            issues.append("REPLAYED_SKILL_OUTCOME")
            continue
        matched.add(original)
        paired += 1
    missing = sum(1 for k, v in skill_map.items() if v["recipe"] in ACTIONS and k not in matched)
    if missing:
        issues.append("SKILL_FEEDBACK_NOT_IN_META_STORE")
    status = "INTEGRITY_HOLD" if issues else (
        "LINKED_SCHEMA_ONLY_NO_INDEPENDENT_ATTESTATION" if paired else "NO_LINKABLE_RECORDS"
    )
    return _result(status, len(skill_rows), len(meta_rows), paired, missing, model_unknown, issues)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print("V657_FEEDBACK_LINEAGE=" + json.dumps(audit(args.root), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Bounded code-defined SELFREFINE repairs for known regressions.

Only code-defined transformations may edit a local working tree. Error evidence,
ledger text, learned strings, JSON payloads, and external content are never
executed or converted into patches. Git is never written here.

A repair is attempted at most once per invocation. Its result is immediately
re-scanned by Main SELFREFINE. Two consecutive verification failures quarantine
that rule until the code-defined rule itself is reviewed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import tempfile
from pathlib import Path
from typing import Any

from safe_runtime import atomic_write_json, atomic_write_text, exclusive_file_lock, safe_read_text

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "MAIN_SELFREFINE_VERIFIED_REPAIR_STATE.json"
SCHEMA = 2
MAX_REPAIRS_PER_RUN = 3
MAX_HISTORY = 100
MAX_TEXT_BYTES = 4_000_000
_ROLLBACK_CACHE: dict[str, dict[str, str]] = {}

NODE24_ACTION_PINS = {
    "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
    "actions/setup-python": "5fda3b95a4ea91299a34e894583c3862153e4b97",
    "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
}

CORE_WORKFLOWS = {
    ".github/workflows/selfrefine-full-repo.yml",
    ".github/workflows/repository-integrity-guard.yml",
    ".github/workflows/runtime-delivery-guard.yml",
    ".github/workflows/instagram-tcg-selfrefine.yml",
    ".github/workflows/code-repair-learning-guard.yml",
    ".github/workflows/tcg-code-repair-learning-guard.yml",
    ".github/workflows/grading-vision-selfrefine-guard.yml",
    ".github/workflows/apply-detailed-collection-intelligence.yml",
    ".github/workflows/ocr-selfrefine-guard.yml",
}
RESOURCE_GUARD_PATH = "test_manual_only_official_verification_v192.py"
FEATURE_CONTRACT_PATH = "feature_contract.py"
OCR_CONTRACT_PATH = "verify_v109_card_identity.py"

ACTION_RULE_ID = "upgrade-core-actions-node24-v1"
RESOURCE_RULE_ID = "close-literal-read-handles-v1"
FEATURE_VISION_RULE_ID = "align-photo-feature-contract-1-4-8-v1"
OCR_COUNT_RULE_ID = "dynamic-feature-contract-count-v1"
ALL_RULE_IDS = (
    ACTION_RULE_ID,
    RESOURCE_RULE_ID,
    FEATURE_VISION_RULE_ID,
    OCR_COUNT_RULE_ID,
)
RULE_PATHS = {
    ACTION_RULE_ID: frozenset(CORE_WORKFLOWS),
    RESOURCE_RULE_ID: frozenset({RESOURCE_GUARD_PATH}),
    FEATURE_VISION_RULE_ID: frozenset({FEATURE_CONTRACT_PATH}),
    OCR_COUNT_RULE_ID: frozenset({OCR_CONTRACT_PATH}),
}

STALE_FEATURE_BLOCK = """        and all(token in page for token in ("sceneDistance", "Camera", "_tcgCapturedFile", "visibilitychange",
                                             "analyzeWhitening", "confirmedSegments")),
        "앞·뒤 파일입력·자동촬영·내부 보더·Hough 선형 결함·백화·카메라 수명주기")
"""
CURRENT_FEATURE_BLOCK = """        and all(token in page for token in ("sceneDistance", "Camera", "_tcgCapturedFile", "visibilitychange",
                                             "confirmedSegments", "hierarchyDefectRisk", "eightZoneWorstRisk"))
        and all(token in vision_engine for token in (
            "analyzeWhitening",
            "quadrantCornerWorstRisk",
            "eightZoneWorst",
            "hierarchyDefectRisk",
        )),
        "앞·뒤 파일입력·자동촬영·1→4→8 비전·독립 코너/엣지·백화·사선광·카메라 수명주기")
"""
STALE_OCR_COUNT = '    assert contract["ok"] and contract["implemented"] == contract["total"] == 25'
CURRENT_OCR_COUNT = """    assert (
        contract["ok"]
        and contract["implemented"] == contract["total"] == len(contract["features"])
    ), json.dumps(contract, ensure_ascii=False, sort_keys=True)"""

_ACTION_RE = re.compile(
    r"(?P<action>actions/(?:checkout|setup-python|upload-artifact))@(?P<sha>[0-9a-f]{40})"
)
_RESOURCE_READ_RE = re.compile(
    r"open\(\s*(?P<quote>['\"])(?P<path>[^'\"]+)(?P=quote)\s*,\s*"
    r"encoding\s*=\s*['\"]utf-8['\"]\s*\)\.read\(\)"
)


def _normalized(relative: str) -> str:
    return str(relative).replace("\\", "/")


def detect_text_issues(relative: str, text: str) -> list[dict[str, str]]:
    relative = _normalized(relative)
    issues: list[dict[str, str]] = []

    if relative == RESOURCE_GUARD_PATH and _RESOURCE_READ_RE.search(text):
        issues.append({
            "stage": "RESOURCE_HANDLE_LEAK_RISK",
            "root_cause": "unclosed literal text read",
            "evidence": "open(..., encoding='utf-8').read() can leave a file handle for GC",
            "fix_rule": RESOURCE_RULE_ID,
        })

    if relative == FEATURE_CONTRACT_PATH and STALE_FEATURE_BLOCK in text:
        issues.append({
            "stage": "FEATURE_CONTRACT_VISION_STALE",
            "root_cause": "front/back feature contract still expects whitening implementation inside index.html",
            "evidence": "1→4→8 vision implementation moved to grading_vision_engine.js",
            "fix_rule": FEATURE_VISION_RULE_ID,
        })

    if relative == OCR_CONTRACT_PATH and STALE_OCR_COUNT in text:
        issues.append({
            "stage": "OCR_FEATURE_COUNT_STALE",
            "root_cause": "OCR contract hard-codes historical feature count",
            "evidence": "feature contract count must follow the declared features list",
            "fix_rule": OCR_COUNT_RULE_ID,
        })

    if relative in CORE_WORKFLOWS:
        stale = []
        for match in _ACTION_RE.finditer(text):
            action = match.group("action")
            expected = NODE24_ACTION_PINS[action]
            if match.group("sha") != expected:
                stale.append(action)
        if stale:
            issues.append({
                "stage": "CI_ACTION_RUNTIME_DEPRECATED",
                "root_cause": "core GitHub Action not pinned to current Node 24 action release",
                "evidence": ", ".join(sorted(set(stale))),
                "fix_rule": ACTION_RULE_ID,
            })
    return issues


def rule_for_issue(issue: dict[str, Any]) -> str | None:
    stage = str(issue.get("stage") or "")
    path = _normalized(str(issue.get("path") or ""))
    if stage == "RESOURCE_HANDLE_LEAK_RISK" and path == RESOURCE_GUARD_PATH:
        return RESOURCE_RULE_ID
    if stage == "CI_ACTION_RUNTIME_DEPRECATED" and path in CORE_WORKFLOWS:
        return ACTION_RULE_ID
    if stage == "FEATURE_CONTRACT_VISION_STALE" and path == FEATURE_CONTRACT_PATH:
        return FEATURE_VISION_RULE_ID
    if stage == "OCR_FEATURE_COUNT_STALE" and path == OCR_CONTRACT_PATH:
        return OCR_COUNT_RULE_ID
    return None



def rule_fingerprint(rule_id: str) -> str:
    """Fingerprint the executable definition of one allowlisted repair rule.

    Historical success is trusted only while this fingerprint is unchanged.
    """
    if rule_id == ACTION_RULE_ID:
        payload: Any = {
            "rule_id": rule_id,
            "paths": sorted(RULE_PATHS[rule_id]),
            "pins": NODE24_ACTION_PINS,
        }
    elif rule_id == RESOURCE_RULE_ID:
        payload = {
            "rule_id": rule_id,
            "paths": sorted(RULE_PATHS[rule_id]),
            "pattern": _RESOURCE_READ_RE.pattern,
            "replacement": "Path(...).read_text(encoding='utf-8')",
        }
    elif rule_id == FEATURE_VISION_RULE_ID:
        payload = {
            "rule_id": rule_id,
            "paths": sorted(RULE_PATHS[rule_id]),
            "before": STALE_FEATURE_BLOCK,
            "after": CURRENT_FEATURE_BLOCK,
        }
    elif rule_id == OCR_COUNT_RULE_ID:
        payload = {
            "rule_id": rule_id,
            "paths": sorted(RULE_PATHS[rule_id]),
            "before": STALE_OCR_COUNT,
            "after": CURRENT_OCR_COUNT,
        }
    else:
        raise ValueError("unknown repair rule")
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:24]


def _empty_rule_stats(rule_id: str) -> dict[str, Any]:
    return {
        "fingerprint": rule_fingerprint(rule_id),
        "attempts": 0,
        "successes": 0,
        "failures": 0,
        "consecutive_failures": 0,
        "quarantined": False,
        "confidence": 0.5,
    }


def _default_state() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "rules": {},
        "history": [],
        "safety": {
            "learned_text_executable": False,
            "learned_patch_text_used": False,
            "git_write": False,
            "code_defined_rules_only": True,
            "max_repairs_per_run": MAX_REPAIRS_PER_RUN,
            "quarantine_after_consecutive_failures": 2,
            "failed_repair_auto_rollback": True,
            "new_regression_auto_rollback": True,
            "rule_fingerprint_required": True,
            "process_safe_state_transaction": True,
        },
    }


def _load_state(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(safe_read_text(path, max_bytes=1_000_000))
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return _default_state()
    if not isinstance(value, dict):
        return _default_state()
    state = _default_state()
    raw_rules = value.get("rules") if isinstance(value.get("rules"), dict) else {}
    for rule_id in ALL_RULE_IDS:
        current_fingerprint = rule_fingerprint(rule_id)
        raw = raw_rules.get(rule_id) if isinstance(raw_rules.get(rule_id), dict) else {}
        if raw.get("fingerprint") != current_fingerprint:
            state["rules"][rule_id] = _empty_rule_stats(rule_id)
            continue
        try:
            attempts = max(0, min(1000, int(raw.get("attempts") or 0)))
            successes = max(0, min(1000, int(raw.get("successes") or 0)))
            failures = max(0, min(1000, int(raw.get("failures") or 0)))
            consecutive = max(0, min(100, int(raw.get("consecutive_failures") or 0)))
        except (TypeError, ValueError, OverflowError):
            state["rules"][rule_id] = _empty_rule_stats(rule_id)
            continue
        state["rules"][rule_id] = {
            "fingerprint": current_fingerprint,
            "attempts": attempts,
            "successes": successes,
            "failures": failures,
            "consecutive_failures": consecutive,
            "quarantined": raw.get("quarantined") is True,
            "confidence": round((successes + 1) / (max(1, attempts) + 2), 4),
        }
    state["history"] = [x for x in (value.get("history") or [])[-MAX_HISTORY:] if isinstance(x, dict)]
    return state

def _save_state(path: Path, state: dict[str, Any]) -> None:
    state["history"] = state.get("history", [])[-MAX_HISTORY:]
    atomic_write_json(path, state, suffix=".verified-repair.tmp")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:20]


def _transform_resource(relative: str, text: str) -> str:
    if _normalized(relative) != RESOURCE_GUARD_PATH:
        return text
    updated = text
    if _RESOURCE_READ_RE.search(updated) and "from pathlib import Path" not in updated:
        if "import unittest\n" in updated:
            updated = updated.replace("import unittest\n", "import unittest\nfrom pathlib import Path\n", 1)
        else:
            return text

    def repl(match: re.Match[str]) -> str:
        literal = repr(match.group("path"))
        return f"Path({literal}).read_text(encoding='utf-8')"

    return _RESOURCE_READ_RE.sub(repl, updated)


def _transform_actions(relative: str, text: str) -> str:
    if _normalized(relative) not in CORE_WORKFLOWS:
        return text

    def repl(match: re.Match[str]) -> str:
        action = match.group("action")
        return f"{action}@{NODE24_ACTION_PINS[action]}"

    return _ACTION_RE.sub(repl, text)


def _transform_feature_contract(relative: str, text: str) -> str:
    if _normalized(relative) != FEATURE_CONTRACT_PATH or STALE_FEATURE_BLOCK not in text:
        return text
    updated = text
    page_line = '    page = safe_read_text(base / "index.html")\n'
    vision_line = '    vision_engine = safe_read_text(base / "grading_vision_engine.js")\n'
    if vision_line not in updated:
        if page_line not in updated:
            return text
        updated = updated.replace(page_line, page_line + vision_line, 1)
    return updated.replace(STALE_FEATURE_BLOCK, CURRENT_FEATURE_BLOCK, 1)


def _transform_ocr_count(relative: str, text: str) -> str:
    if _normalized(relative) != OCR_CONTRACT_PATH:
        return text
    return text.replace(STALE_OCR_COUNT, CURRENT_OCR_COUNT, 1)


def transform_for_rule(rule_id: str, relative: str, text: str) -> str:
    if rule_id == RESOURCE_RULE_ID:
        return _transform_resource(relative, text)
    if rule_id == ACTION_RULE_ID:
        return _transform_actions(relative, text)
    if rule_id == FEATURE_VISION_RULE_ID:
        return _transform_feature_contract(relative, text)
    if rule_id == OCR_COUNT_RULE_ID:
        return _transform_ocr_count(relative, text)
    return text


def apply_issues(
    issues: list[dict[str, Any]],
    *,
    root: Path = ROOT,
    state_path: Path = STATE,
    max_repairs: int = MAX_REPAIRS_PER_RUN,
) -> dict[str, Any]:
    with exclusive_file_lock(state_path):
        state = _load_state(state_path)
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    limit = max(0, min(MAX_REPAIRS_PER_RUN, int(max_repairs)))

    ordered_issues = sorted(
        (row for row in issues if isinstance(row, dict)),
        key=lambda row: (
            row.get("learned_solution_reuse") is not True,
            -float(row.get("learned_solution_confidence") or 0.0),
            str(row.get("path") or ""),
            str(row.get("stage") or ""),
        ),
    )

    for issue in ordered_issues:
        if len(applied) >= limit:
            break
        if issue.get("state") not in {None, "open"}:
            continue
        if issue.get("auto_repair_allowed") is False:
            skipped.append({
                "rule_id": str(issue.get("auto_repair_rule") or ""),
                "path": _normalized(str(issue.get("path") or "")),
                "reason": "error_signature_quarantined_or_unverified",
            })
            continue
        rule_id = rule_for_issue(issue)
        relative = _normalized(str(issue.get("path") or ""))
        if not rule_id:
            continue
        key = (rule_id, relative)
        if key in seen:
            continue
        seen.add(key)

        stats = state.setdefault("rules", {}).setdefault(rule_id, _empty_rule_stats(rule_id))
        if stats.get("quarantined") is True or int(stats.get("consecutive_failures") or 0) >= 2:
            skipped.append({"rule_id": rule_id, "path": relative, "reason": "quarantined"})
            continue

        if relative not in RULE_PATHS.get(rule_id, frozenset()):
            skipped.append({"rule_id": rule_id, "path": relative, "reason": "path_not_allowlisted"})
            continue

        target = root / relative
        try:
            if target.is_symlink() or not target.is_file():
                raise OSError("target is not a regular file")
            before = safe_read_text(target, max_bytes=MAX_TEXT_BYTES)
        except (OSError, ValueError, UnicodeError):
            skipped.append({"rule_id": rule_id, "path": relative, "reason": "unsafe_or_unreadable"})
            continue

        after = transform_for_rule(rule_id, relative, before)
        if after == before:
            skipped.append({"rule_id": rule_id, "path": relative, "reason": "precondition_not_met"})
            continue

        atomic_write_text(target, after, suffix=".verified-self-heal.tmp")
        rollback_token = secrets.token_hex(16)
        _ROLLBACK_CACHE[rollback_token] = {
            "path": relative,
            "before": before,
            "after_hash": _hash(after),
        }
        applied.append({
            "rule_id": rule_id,
            "path": relative,
            "stage": str(issue.get("stage") or ""),
            "error_signature": str(issue.get("error_signature") or "")[:80],
            "error_code": str(issue.get("error_code") or "")[:160],
            "error_family": str(issue.get("error_family") or "")[:80],
            "learned_solution_reuse": issue.get("learned_solution_reuse") is True,
            "rule_fingerprint": rule_fingerprint(rule_id),
            "rollback_token": rollback_token,
            "before_hash": _hash(before),
            "after_hash": _hash(after),
        })

    return {
        "applied_count": len(applied),
        "applied": applied,
        "skipped": skipped,
        "learned_text_executable": False,
        "learned_patch_text_used": False,
        "git_write": False,
        "code_defined_rules_only": True,
        "failed_repair_auto_rollback": True,
        "new_regression_auto_rollback": True,
    }


def _open_error_keys(rows: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {
        (str(row.get("stage") or ""), _normalized(str(row.get("path") or "")))
        for row in rows
        if isinstance(row, dict) and row.get("state") == "open"
    }


def rollback_failed_repairs(
    applied: list[dict[str, Any]],
    baseline_errors: list[dict[str, Any]],
    remaining_errors: list[dict[str, Any]],
    *,
    root: Path = ROOT,
) -> dict[str, Any]:
    """Rollback any self-modification that failed verification or introduced regression."""
    baseline_keys = _open_error_keys(baseline_errors)
    remaining_keys = _open_error_keys(remaining_errors)
    new_regressions = sorted(remaining_keys - baseline_keys)
    restored = kept = conflicts = 0
    failed_tokens: list[str] = []

    for item in applied:
        token = str(item.get("rollback_token") or "")
        backup = _ROLLBACK_CACHE.pop(token, None) if token else None
        key = (str(item.get("stage") or ""), _normalized(str(item.get("path") or "")))
        failed = key in remaining_keys or bool(new_regressions)
        if not failed:
            kept += 1
            item["rollback_outcome"] = "verified_kept"
            continue

        item["verification_forced_failed"] = True
        failed_tokens.append(token)
        if not isinstance(backup, dict):
            item["rollback_outcome"] = "rollback_backup_missing"
            conflicts += 1
            continue

        relative = _normalized(str(item.get("path") or ""))
        rule_id = str(item.get("rule_id") or "")
        if relative not in RULE_PATHS.get(rule_id, frozenset()):
            item["rollback_outcome"] = "rollback_path_not_allowlisted"
            conflicts += 1
            continue

        target = root / relative
        try:
            if target.is_symlink() or not target.is_file():
                raise OSError("target is not a regular file")
            current = safe_read_text(target, max_bytes=MAX_TEXT_BYTES)
            if _hash(current) != str(backup.get("after_hash") or ""):
                item["rollback_outcome"] = "rollback_conflict_current_file_changed"
                conflicts += 1
                continue
            before = str(backup.get("before") or "")
            if _hash(before) != str(item.get("before_hash") or ""):
                item["rollback_outcome"] = "rollback_backup_hash_mismatch"
                conflicts += 1
                continue
            atomic_write_text(target, before, suffix=".verified-self-heal-rollback.tmp")
            item["rollback_outcome"] = "restored_after_failed_verification"
            restored += 1
        except (OSError, ValueError, UnicodeError):
            item["rollback_outcome"] = "rollback_io_failure"
            conflicts += 1

    return {
        "restored": restored,
        "verified_kept": kept,
        "rollback_conflicts": conflicts,
        "new_regressions": [
            {"stage": stage, "path": path} for stage, path in new_regressions
        ],
        "failed_repair_tokens": [token for token in failed_tokens if token],
        "fail_closed": True,
    }


def record_verification(
    applied: list[dict[str, Any]],
    remaining_errors: list[dict[str, Any]],
    *,
    state_path: Path = STATE,
) -> dict[str, Any]:
    open_keys = _open_error_keys(remaining_errors)
    passed = failed = quarantined = 0

    with exclusive_file_lock(state_path):
        state = _load_state(state_path)
        for item in applied:
            rule_id = str(item.get("rule_id") or "")
            path = _normalized(str(item.get("path") or ""))
            stage = str(item.get("stage") or "")
            if rule_id not in ALL_RULE_IDS:
                continue
            stats = state.setdefault("rules", {}).setdefault(rule_id, _empty_rule_stats(rule_id))
            current_fingerprint = rule_fingerprint(rule_id)
            if stats.get("fingerprint") != current_fingerprint:
                stats = _empty_rule_stats(rule_id)
                state["rules"][rule_id] = stats

            stats["attempts"] = min(1000, int(stats.get("attempts") or 0) + 1)
            ok = (
                item.get("verification_forced_failed") is not True
                and (stage, path) not in open_keys
            )
            if ok:
                stats["successes"] = min(1000, int(stats.get("successes") or 0) + 1)
                stats["consecutive_failures"] = 0
                stats["quarantined"] = False
                passed += 1
                outcome = "verified_pass"
            else:
                stats["failures"] = min(1000, int(stats.get("failures") or 0) + 1)
                stats["consecutive_failures"] = min(100, int(stats.get("consecutive_failures") or 0) + 1)
                stats["quarantined"] = stats["consecutive_failures"] >= 2
                failed += 1
                quarantined += int(stats["quarantined"])
                outcome = "verification_failed"

            attempts = max(1, int(stats.get("attempts") or 0))
            stats["fingerprint"] = current_fingerprint
            stats["confidence"] = round((int(stats.get("successes") or 0) + 1) / (attempts + 2), 4)
            state.setdefault("history", []).append({
                "rule_id": rule_id,
                "rule_fingerprint": current_fingerprint,
                "path": path,
                "stage": stage,
                "outcome": outcome,
                "rollback_outcome": str(item.get("rollback_outcome") or "")[:80],
                "before_hash": str(item.get("before_hash") or "")[:20],
                "after_hash": str(item.get("after_hash") or "")[:20],
            })
            token = str(item.get("rollback_token") or "")
            if token:
                _ROLLBACK_CACHE.pop(token, None)

        _save_state(state_path, state)

    return {
        "verified_pass": passed,
        "verification_failed": failed,
        "quarantined": quarantined,
        "state_path": state_path.name,
        "learned_text_executable": False,
        "code_defined_rules_only": True,
        "rule_fingerprint_required": True,
        "process_safe_state_transaction": True,
    }

def self_test() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        resource = root / RESOURCE_GUARD_PATH
        resource.write_text(
            "import unittest\n\n"
            "x=open('a.js',encoding='utf-8').read()\n",
            encoding="utf-8",
        )
        workflow_rel = ".github/workflows/selfrefine-full-repo.yml"
        workflow = root / workflow_rel
        workflow.parent.mkdir(parents=True)
        workflow.write_text(
            "steps:\n"
            "  - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262\n"
            "  - uses: actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065\n",
            encoding="utf-8",
        )
        state = root / "state.json"
        issues = []
        for relative, target in ((RESOURCE_GUARD_PATH, resource), (workflow_rel, workflow)):
            for item in detect_text_issues(relative, target.read_text(encoding="utf-8")):
                issues.append({"path": relative, "state": "open", **item})
        result = apply_issues(issues, root=root, state_path=state)
        assert result["applied_count"] == 2, result
        assert "Path('a.js').read_text" in resource.read_text(encoding="utf-8")
        updated_workflow = workflow.read_text(encoding="utf-8")
        assert NODE24_ACTION_PINS["actions/checkout"] in updated_workflow
        assert NODE24_ACTION_PINS["actions/setup-python"] in updated_workflow
        assert not detect_text_issues(RESOURCE_GUARD_PATH, resource.read_text(encoding="utf-8"))
        assert not detect_text_issues(workflow_rel, updated_workflow)

        finalized = rollback_failed_repairs(result["applied"], issues, [], root=root)
        assert finalized["verified_kept"] == 2, finalized
        verified = record_verification(result["applied"], [], state_path=state)
        assert verified["verified_pass"] == 2

        action_item = next(x for x in result["applied"] if x["rule_id"] == ACTION_RULE_ID)
        remaining = [{"stage": action_item["stage"], "path": action_item["path"], "state": "open"}]
        record_verification([action_item], remaining, state_path=state)
        record_verification([action_item], remaining, state_path=state)
        state_payload = json.loads(state.read_text(encoding="utf-8"))
        assert state_payload["rules"][ACTION_RULE_ID]["quarantined"] is True

        workflow.write_text(
            "steps:\n  - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262\n",
            encoding="utf-8",
        )
        stale_issue = [{
            "path": workflow_rel,
            "state": "open",
            **detect_text_issues(workflow_rel, workflow.read_text(encoding="utf-8"))[0],
        }]
        blocked = apply_issues(stale_issue, root=root, state_path=state)
        assert blocked["applied_count"] == 0
        assert blocked["skipped"][0]["reason"] == "quarantined"

    print("Verified code-defined SELFREFINE repair rules: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        return self_test()
    raise SystemExit("Use through Main SELFREFINE; direct arbitrary patch input is not supported.")


if __name__ == "__main__":
    raise SystemExit(main())

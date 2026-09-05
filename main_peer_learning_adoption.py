#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from shared_self_learning.peer_learning import evaluate_main_peer_adoption, normalize_peer_lesson

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "MARKET_ANALYSIS_PEER_PREVENTION_RULES.json"


def _read_state(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"version": 1, "rules": []}
    if not isinstance(value, dict) or not isinstance(value.get("rules"), list):
        raise ValueError("invalid Main peer prevention-rule state")
    return value


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            temp = Path(handle.name)
        temp.replace(path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink(missing_ok=True)


def adopt_peer_lesson(
    peer_lesson: dict[str, Any],
    *,
    reproduction_pass: bool,
    root_cause_reconfirmed: bool,
    minimal_scope_fix: bool,
    local_regression_pass: bool,
    full_regression_pass: bool,
    crosscheck_status: str = "single-system-only",
    safer_fix_selected: bool = False,
    selected_fix_pattern: str | None = None,
    state_path: Path = STATE,
) -> dict[str, Any]:
    peer = normalize_peer_lesson("instagram_content", peer_lesson)
    decision = evaluate_main_peer_adoption(
        peer,
        reproduction_pass=reproduction_pass,
        root_cause_reconfirmed=root_cause_reconfirmed,
        minimal_scope_fix=minimal_scope_fix,
        local_regression_pass=local_regression_pass,
        full_regression_pass=full_regression_pass,
        crosscheck_status=crosscheck_status,
        safer_fix_selected=safer_fix_selected,
        selected_fix_pattern=selected_fix_pattern,
    )
    if not decision["adoption_allowed"]:
        return decision

    rule = dict(decision["local_prevention_rule"])
    if "prevention_rule_id" in peer:
        assert rule["prevention_rule_id"] != peer["prevention_rule_id"]
    if any(key in rule for key in ("peer_prevention_rule_id", "prevention_rule", "raw_log", "error_ledger")):
        raise AssertionError("peer internal rule/state leaked into Main local prevention rule")

    state = _read_state(state_path)
    existing = {str(row.get("prevention_rule_id")) for row in state["rules"] if isinstance(row, dict)}
    if rule["prevention_rule_id"] not in existing:
        state["rules"].append(rule)
        _write_atomic(state_path, state)
    decision["saved_to_main_local_state"] = True
    decision["state_file"] = state_path.name
    return decision


def self_test() -> None:
    peer = {
        "lesson_id": "IG-L1",
        "subsystem": "source_parser",
        "issue_class": "empty_parse",
        "trigger_condition": "HTTP 200 but zero usable rows",
        "symptom_summary": "shell without usable rows",
        "root_cause_class": "dynamic_page_shell",
        "fix_pattern": "switch to verified alternate source/parser",
        "prevention_rule_id": "IG-RULE-SECRET",
        "verification_result": "passed",
        "regression_pass": True,
        "recurrence_count": 3,
        "applicable_scope": "both",
        "confidence_level": "high",
    }
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.json"
        blocked = adopt_peer_lesson(
            peer,
            reproduction_pass=True,
            root_cause_reconfirmed=True,
            minimal_scope_fix=True,
            local_regression_pass=True,
            full_regression_pass=False,
            state_path=path,
        )
        assert blocked["adoption_allowed"] is False
        assert not path.exists()

        accepted = adopt_peer_lesson(
            peer,
            reproduction_pass=True,
            root_cause_reconfirmed=True,
            minimal_scope_fix=True,
            local_regression_pass=True,
            full_regression_pass=True,
            state_path=path,
        )
        assert accepted["adoption_allowed"] is True
        state = json.loads(path.read_text(encoding="utf-8"))
        rule = state["rules"][0]
        assert rule["learned_from_peer"] == "IG-L1"
        assert rule["prevention_rule_id"] != "IG-RULE-SECRET"
        assert "peer_prevention_rule_id" not in rule

        conflict_blocked = adopt_peer_lesson(
            peer,
            reproduction_pass=True,
            root_cause_reconfirmed=True,
            minimal_scope_fix=True,
            local_regression_pass=True,
            full_regression_pass=True,
            crosscheck_status="conflicting-fix",
            safer_fix_selected=False,
            state_path=path,
        )
        assert conflict_blocked["adoption_allowed"] is False
    print("Main peer learning adoption gate: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lesson")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--reproduction-pass", action="store_true")
    parser.add_argument("--root-cause-reconfirmed", action="store_true")
    parser.add_argument("--minimal-scope-fix", action="store_true")
    parser.add_argument("--local-regression-pass", action="store_true")
    parser.add_argument("--full-regression-pass", action="store_true")
    parser.add_argument("--crosscheck-status", default="single-system-only")
    parser.add_argument("--safer-fix-selected", action="store_true")
    parser.add_argument("--selected-fix-pattern")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.lesson:
        raise SystemExit("--lesson is required unless --self-test is used")
    lesson = json.loads(Path(args.lesson).read_text(encoding="utf-8"))
    result = adopt_peer_lesson(
        lesson,
        reproduction_pass=args.reproduction_pass,
        root_cause_reconfirmed=args.root_cause_reconfirmed,
        minimal_scope_fix=args.minimal_scope_fix,
        local_regression_pass=args.local_regression_pass,
        full_regression_pass=args.full_regression_pass,
        crosscheck_status=args.crosscheck_status,
        safer_fix_selected=args.safer_fix_selected,
        selected_fix_pattern=args.selected_fix_pattern,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["adoption_allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

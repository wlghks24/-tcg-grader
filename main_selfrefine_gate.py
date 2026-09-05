#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import security_self_audit
import selfrefine_full_repo as core
import selfrefine_error_quarantine as error_quarantine
import selfrefine_resolution_research as resolution_research
import verified_code_repair_rules as verified_repairs
from shared_self_learning import SHARED_SELF_LEARNING_CONTRACT_VERSION
from shared_self_learning.engine import enrich_error

ROOT = Path(__file__).resolve().parent
POLICY = json.loads((ROOT / "selfrefine_domain_policy.json").read_text(encoding="utf-8"))
EXCLUDES = tuple(POLICY["domains"]["main"]["exclude_prefixes"])
LEDGER = ROOT / POLICY["domains"]["main"]["ledger"]
REPAIR_STATE = ROOT / POLICY["domains"]["main"]["state_files"]["verified_repair"]
ERROR_QUARANTINE_STATE = ROOT / POLICY["domains"]["main"]["state_files"]["error_quarantine"]
RESOLUTION_LEARNING_STATE = ROOT / POLICY["domains"]["main"]["state_files"]["resolution_learning"]


def _is_main_path(relative: str) -> bool:
    normalized = str(relative).replace("\\", "/")
    return not any(normalized.startswith(prefix) for prefix in EXCLUDES)


def tracked_main_files():
    for relative, path, is_symlink in core.integrity.tracked_entries():
        if not _is_main_path(relative):
            continue
        if is_symlink or path.suffix.lower() not in core.AUDIT_SUFFIXES:
            continue
        yield relative, path


def scan_main_security():
    errors = []
    for finding in security_self_audit.scan_repository(ROOT):
        relative = str(finding.get("path") or "repository")
        if not _is_main_path(relative):
            continue
        if security_self_audit.SEVERITY_ORDER.get(str(finding.get("severity")), 0) < security_self_audit.SEVERITY_ORDER["high"]:
            continue
        errors.append(core.make_issue(
            "SECURITY_HIGH", relative, str(finding.get("rule") or "security finding"),
            str(finding.get("evidence") or finding.get("message") or ""),
            "high/critical 보안 finding을 해결하고 Main SELFREFINE 회귀검사를 재실행",
        ))
    return errors


def _enrich(rows):
    return [enrich_error("main", row) for row in rows]


def scan_once():
    errors = []
    files = list(tracked_main_files())
    for relative, path in files:
        errors.extend(core.scan_file(relative, path))
        if len(errors) >= core.MAX_ERRORS:
            break
    if len(errors) < core.MAX_ERRORS:
        errors.extend(scan_main_security())
    return _enrich(errors[:core.MAX_ERRORS]), len(files)


def run(cycles: int):
    original_scan_once = core.scan_once
    original_ledger = core.LEDGER_PATH
    try:
        core.scan_once = scan_once
        core.LEDGER_PATH = LEDGER
        result = core.run(cycles, path=LEDGER)
        open_errors = [
            row for row in result.get("errors", [])
            if isinstance(row, dict) and row.get("state") == "open"
        ]
        isolation = error_quarantine.observe_open_errors(
            open_errors,
            state_path=ERROR_QUARANTINE_STATE,
        )
        resolution_research_result = resolution_research.observe_errors(
            isolation.get("errors", []),
            root=ROOT,
            state_path=RESOLUTION_LEARNING_STATE,
        )
        repair = verified_repairs.apply_issues(
            isolation.get("errors", []),
            root=ROOT,
            state_path=REPAIR_STATE,
        )
        if repair.get("applied_count"):
            post_repair_result = core.run(1, path=LEDGER)
            rollback = verified_repairs.rollback_failed_repairs(
                repair.get("applied", []),
                open_errors,
                post_repair_result.get("errors", []),
                root=ROOT,
            )
            verification = verified_repairs.record_verification(
                repair.get("applied", []),
                post_repair_result.get("errors", []),
                state_path=REPAIR_STATE,
            )
            resolution_learning = error_quarantine.record_repair_outcomes(
                repair.get("applied", []),
                post_repair_result.get("errors", []),
                state_path=ERROR_QUARANTINE_STATE,
            )
            resolution_learning_stage = resolution_research.stage_repairs(
                repair.get("applied", []),
                state_path=RESOLUTION_LEARNING_STATE,
            )
            result = (
                core.run(1, path=LEDGER)
                if rollback.get("restored") or rollback.get("rollback_conflicts")
                else post_repair_result
            )
        else:
            rollback = {
                "restored": 0,
                "verified_kept": 0,
                "rollback_conflicts": 0,
                "new_regressions": [],
                "fail_closed": True,
            }
            verification = {
                "verified_pass": 0,
                "verification_failed": 0,
                "quarantined": 0,
                "state_path": REPAIR_STATE.name,
            }
            resolution_learning = {
                "verified_resolution_learned": 0,
                "verification_failed": 0,
                "newly_quarantined": 0,
                "state_path": ERROR_QUARANTINE_STATE.name,
            }
            resolution_learning_stage = {
                "pending_full_regression": 0,
                "full_regression_required_before_learning": True,
                "learned_now": 0,
            }
        result["verified_self_heal"] = {
            "isolation": isolation,
            "repair": repair,
            "rollback": rollback,
            "verification": verification,
            "resolution_learning": resolution_learning,
            "resolution_research": resolution_research_result,
            "resolution_learning_stage": resolution_learning_stage,
        }
        result.setdefault("summary", {}).update({
            "isolated_error_codes": isolation.get("summary", {}).get("isolated_count", 0),
            "learned_solution_reuse": isolation.get("summary", {}).get("learned_solution_reuse", 0),
            "quarantined_error_codes": isolation.get("summary", {}).get("quarantined_count", 0),
            "verified_resolutions_learned": resolution_learning.get("verified_resolution_learned", 0),
            "self_modify_rollbacks": rollback.get("restored", 0),
            "self_modify_rollback_conflicts": rollback.get("rollback_conflicts", 0),
            "new_errors_researched": resolution_research_result.get("new_error_count", 0),
            "repository_files_analyzed_for_errors": resolution_research_result.get("repository_files_scanned", 0),
            "verified_resolution_reuse_candidates": resolution_research_result.get("known_verified_resolution_count", 0),
            "resolution_lessons_pending_full_regression": resolution_learning_stage.get("pending_full_regression", 0),
        })
        result.setdefault("safety", {}).update({
            "verified_code_defined_auto_repair": True,
            "learned_patch_text_used": False,
            "learned_text_executable": False,
            "git_write": False,
            "repair_quarantine_after_consecutive_failures": 2,
            "error_code_isolation": True,
            "verified_resolution_learning": True,
            "unknown_error_auto_repair": False,
            "failed_repair_auto_rollback": True,
            "new_regression_auto_rollback": True,
            "repair_rule_fingerprint_required": True,
            "process_safe_learning_state": True,
            "full_repository_error_impact_analysis": True,
            "official_source_first_error_research": True,
            "bounded_official_network_error_research": True,
            "research_network_allowlist_only": True,
            "research_raw_body_persisted": False,
            "research_text_executable": False,
            "search_result_patch_generation": False,
            "full_regression_before_resolution_learning": True,
            "pending_resolution_rule_binding_required": True,
            "pending_resolution_after_hash_required": True,
            "stale_pending_resolution_not_promoted": True,
            "rolled_back_repair_not_staged_for_learning": True,
            "clean_run_skips_redundant_impact_scan": True,
            "transitive_dependency_impact_analysis": True,
        })
        return result
    finally:
        core.scan_once = original_scan_once
        core.LEDGER_PATH = original_ledger


def self_test():
    assert _is_main_path("collector_self_healing.py")
    assert _is_main_path("shared_self_learning/engine.py")
    assert not _is_main_path("instagram_tcg_content/selfrefine_gate.py")
    assert LEDGER.name == "MAIN_SELFREFINE_ERROR_LEDGER.json"
    assert REPAIR_STATE.name == "MAIN_SELFREFINE_VERIFIED_REPAIR_STATE.json"
    assert ERROR_QUARANTINE_STATE.name == "MAIN_SELFREFINE_ERROR_QUARANTINE_STATE.json"
    assert RESOLUTION_LEARNING_STATE.name == "MAIN_SELFREFINE_RESOLUTION_LEARNING_STATE.json"
    assert POLICY["rules"]["shared_self_learning_code"] is True
    assert POLICY["rules"]["shared_self_learning_state"] is False
    assert POLICY["rules"]["cross_domain_learning_state_merge"] is False
    assert POLICY["rules"]["failed_self_modify_auto_rollback"] is True
    assert POLICY["rules"]["repair_rule_fingerprint_required"] is True
    assert POLICY["rules"]["process_safe_selfrefine_state"] is True
    assert POLICY["rules"]["new_error_full_repository_analysis"] is True
    assert POLICY["rules"]["new_error_official_source_research"] is True
    assert POLICY["rules"]["new_error_bounded_official_network_research"] is True
    assert POLICY["rules"]["research_network_allowlist_only"] is True
    assert POLICY["rules"]["research_raw_body_persisted"] is False
    assert POLICY["rules"]["research_text_executable"] is False
    assert POLICY["rules"]["search_result_patch_generation"] is False
    assert POLICY["rules"]["full_regression_before_resolution_learning"] is True
    assert POLICY["rules"]["pending_resolution_rule_binding_required"] is True
    assert POLICY["rules"]["pending_resolution_after_hash_required"] is True
    assert POLICY["rules"]["stale_pending_resolution_not_promoted"] is True
    assert POLICY["rules"]["rolled_back_repair_not_staged_for_learning"] is True
    assert POLICY["rules"]["clean_run_skips_redundant_impact_scan"] is True
    assert POLICY["rules"]["transitive_dependency_impact_analysis"] is True
    assert SHARED_SELF_LEARNING_CONTRACT_VERSION >= 3
    left = enrich_error("main", {"stage": "HTTP_429", "path": "a.py", "evidence": "rate limited"})
    right = enrich_error("instagram_content", {"stage": "HTTP_429", "path": "a.py", "evidence": "rate limited"})
    assert left["shared_learning_key"] != right["shared_learning_key"]
    assert left["shared_retry_bucket"] == right["shared_retry_bucket"]
    print("Main SELFREFINE domain isolation + shared stateless learning algorithms: PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    result = run(max(1, min(5, args.cycles)))
    print(json.dumps(result["summary"], ensure_ascii=False))
    return 0 if result["summary"]["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

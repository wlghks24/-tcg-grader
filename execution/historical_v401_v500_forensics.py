#!/usr/bin/env python3
"""W401–W500 selected historical source-to-test forensic slice (READ ONLY).

Exact baseline Git objects and selected assertions are checked; source text is
never executed/imported. This is not a 100-version audit, tablet test or score.
"""
from __future__ import annotations
import argparse
import ast
import json
import re
import subprocess
from pathlib import Path
from typing import Any

BASE = "6c78831bbb6e188717f86ef90243a836d2e0b67a"
PARENT_LEDGER = "execution/evidence/version_review_findings_v001_v879.json"
PARENT_LEDGER_BLOB = "d2347527056b5b8ec06a9774df50f216219dfa10"
PINNED = {
    "test_promoted_tcg_source_monitor_v413.py": "d1913fad52c76b1b95427aab7b6f86ee8c25a7c1",
    "promoted_tcg_source_monitor_v413.py": "d257323edcff68f049894ac087d79936ba6ed500",
    "test_tablet_gpt_tcg_grader_sync_v426.py": "9cb7b9d956ff740e073f95fb3babd3db4081206d",
    "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V426.json": "e5ef596f39ed49138a74bc1d716f4691043d97df",
    "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v426.json": "3eab9eee22b20b70c4ad930621776b2f1b171d7e",
    "test_tablet_category_focus_v430.py": "984fa61eabf5b2cacb13ea91cac2180326919647",
    "test_tcg_discovery_inbox_v437.py": "7abf0f7b1c51b586dbc8b5aa8abfaa3f500d8403",
    "tcg_discovery_inbox_v437.py": "35548ad93c1177c6c3e489bd2a6e6b2ffa729b5e",
    "test_main_tablet_only_learning_v468.py": "df58da22b7b940a0deee4acc52592ab73715249f",
    "main": "20569af82b1c48906bf2b4641983cfe13a6d651e",
    "TABLET_SCHEDULED_UPDATE.sh": "2b30b108928fb41436182e20fadbb262aaae2135",
    "test_tcg_market_home_v485.py": "18109e03d73e9bb005338c3c3eb72a900af45123",
    "test_grade_context_purchase_v489.py": "e843edeaa7b947e4fc5acc889e553b992afb44fb",
}
CASES = {
    413: ("test_promoted_tcg_source_monitor_v413.py", "MODELLED_SOURCE_FETCH_NOT_LIVE"),
    426: ("test_tablet_gpt_tcg_grader_sync_v426.py", "SYNC_CONTRACT_NOT_DEVICE_RECEIPT"),
    430: ("test_tablet_category_focus_v430.py", "SOURCE_STRING_ASSERTIONS_NOT_TOUCH_QA"),
    437: ("test_tcg_discovery_inbox_v437.py", "SYNTHETIC_URLS_NOT_LIVE_OFFICIAL_VERIFICATION"),
    468: ("test_main_tablet_only_learning_v468.py", "LOCAL_ENTRYPOINT_STRINGS_NOT_TERMUX_RUN"),
    485: ("test_tcg_market_home_v485.py", "STATIC_AND_NODE_SYNTAX_NOT_RENDERED_SCREENSHOT"),
    489: ("test_grade_context_purchase_v489.py", "FIXTURE_IDENTITY_NOT_PURCHASE_OR_AVAILABILITY"),
}
FINDING_IDS = ["W401-F001", "W401-F002", "W401-F003", "W401-F004",
               "W401-F005", "W401-F006", "W401-F007", "W401-F008"]


def git(root: Path, *args: str) -> bytes:
    p = subprocess.run(["git", *args], cwd=root, capture_output=True,
                       check=False, timeout=50)
    if p.returncode:
        raise ValueError("git_original_provenance_unavailable:" + args[0])
    return p.stdout


def original(root: Path, path: str, blob: str) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{40}", blob):
        raise ValueError("bad_expected_git_blob")
    if path.startswith("/") or ".." in path.split("/") or "\\" in path:
        raise ValueError("unsafe_historical_path")
    entry = git(root, "ls-tree", "-z", BASE, "--", path).split(b"\0")
    if len(entry) != 2 or not entry[0]:
        raise ValueError("missing_original_file:" + path)
    meta, sep, returned = entry[0].partition(b"\t")
    if not sep or returned.decode("utf-8", "strict") != path:
        raise ValueError("wrong_original_path")
    mode, kind, got = meta.decode("ascii").split()
    if kind != "blob" or mode not in ("100644", "100755") or got != blob:
        raise ValueError("original_git_blob_mismatch:" + path)
    return git(root, "show", BASE + ":" + path)


def analyze(files: dict[str, bytes], parent: dict[str, Any]) -> dict[str, Any]:
    if parent.get("schema") != "tcg-version-scoped-findings/v1":
        raise ValueError("invalid_parent_findings")
    if parent.get("baseline_main_sha") != BASE:
        raise ValueError("parent_baseline_drift")
    previous = parent.get("findings")
    if not isinstance(previous, list) or not previous:
        raise ValueError("empty_parent_findings")
    ids = [row.get("id") for row in previous if isinstance(row, dict)]
    if len(ids) != len(set(ids)) or "W401-F001" not in ids:
        raise ValueError("missing_prior_w401_protection_finding")
    def check(path: str, token: str, reason: str) -> None:
        if token not in files[path].decode("utf-8", "strict"):
            raise ValueError(reason)
    check("test_promoted_tcg_source_monitor_v413.py",
          "test_failed_probe_does_not_erase_previous_verified_depth",
          "missing_v413_partial_failure_guard")
    check("promoted_tcg_source_monitor_v413.py", "atomic_write_json(",
          "missing_v413_runtime_write_disclosure")
    check("test_tablet_category_focus_v430.py",
          "test_category_opens_menu_only_not_every_long_detail_surface",
          "missing_v430_static_visibility_guard")
    check("test_tcg_discovery_inbox_v437.py", "https://official.example/game",
          "missing_v437_synthetic_origin")
    check("tcg_discovery_inbox_v437.py", "p.scheme==\"https\" and bool(p.hostname)",
          "missing_v437_https_only_gate")
    check("test_main_tablet_only_learning_v468.py", "local-only|cloud-off)",
          "missing_v468_local_only_guard")
    check("test_tcg_market_home_v485.py", "shutil.which(\"node\")",
          "missing_v485_node_syntax_scope")
    check("test_grade_context_purchase_v489.py",
          "PASS: sixteen exact card and edition identity cases",
          "missing_v489_fixture_scope")

    contract = json.loads(files[
        "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V426.json"])
    watch = contract.get("freshness_watch", {})
    if "grading_" not in watch.get("path_prefixes", []):
        raise ValueError("missing_v426_protected_grading_prefix")
    if contract.get("candidate_sync", {}).get("requires_exact_watched_path_match") is not True:
        raise ValueError("weakened_v426_exact_path_contract")
    receipt = json.loads(files[
        "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v426.json"])
    verification = receipt.get("verification", {})
    if (verification.get("physical_tablet_runtime_verified") is not False
            or verification.get("physical_drive_readback_verified") is not False):
        raise ValueError("unsupported_v426_device_proof")
    if "assert_v426_successor(self)" not in files[
            "test_tablet_gpt_tcg_grader_sync_v426.py"].decode("utf-8"):
        raise ValueError("missing_v426_successor_assertion")
    rows = []
    for version, (test_path, caveat) in sorted(CASES.items()):
        tree = ast.parse(files[test_path].decode("utf-8"), filename=test_path)
        tests = sorted(set(n.name for n in ast.walk(tree)
                           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                           and n.name.startswith("test_")))
        if not tests:
            raise ValueError("missing_selected_version_tests")
        rows.append({
            "version": version, "test_source": test_path,
            "original_git_blob": PINNED[test_path], "test_functions_found": len(tests),
            "test_function_names": tests, "evidence_scope": caveat,
            "historical_source_text_review": "SELECTED_PINNED_SOURCE_AND_ASSERTIONS_ONLY",
            "exact_head_runtime_execution": "NOT_PERFORMED_BY_FORENSIC",
            "complete_version_review": False, "quality_score": None,
        })
    return {
        "schema": "tcg-historical-w401-w500-forensics/v1",
        "baseline_main_sha": BASE,
        "selected_versions": sorted(CASES),
        "selected_source_and_test_blob_count": len(PINNED),
        "read_only_pinned_originals": True,
        "previous_finding_ids": ids,
        "previous_finding_count": len(ids),
        "new_gap_finding_ids": FINDING_IDS[1:],
        "continuing_prior_protection": FINDING_IDS[0],
        "cumulative_issues_not_full_review": True,
        "v426_device_verified": False,
        "rows": rows,
        "completed_full_version_reviews_in_w401": 0,
        "quality_score": None,
        "deployment": "HOLD_DEVICE_UNVERIFIED",
        "status": "SELECTED_SOURCE_TO_TEST_SCOPE_ONLY",
    }


def inspect(root: Path) -> dict[str, Any]:
    root = root.resolve()
    git(root, "merge-base", "--is-ancestor", BASE, "HEAD")
    files = {name: original(root, name, blob) for name, blob in PINNED.items()}
    head = git(root, "rev-parse", "--verify", "HEAD^{commit}").decode().strip()
    parent_raw = git(root, "show", head + ":" + PARENT_LEDGER)
    parent_blob = git(root, "ls-tree", "-z", head, "--", PARENT_LEDGER).split(b"\0")[0]
    if not parent_blob or parent_blob.split(b"\t", 1)[0].split()[-1].decode() != PARENT_LEDGER_BLOB:
        raise ValueError("parent_review_ledger_drift")
    return analyze(files, json.loads(parent_raw))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    a = p.parse_args()
    try:
        result = inspect(a.repo_root)
    except (OSError, UnicodeError, ValueError, subprocess.TimeoutExpired) as ex:
        print(json.dumps({"status": "HOLD", "reason": str(ex)[:180]}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

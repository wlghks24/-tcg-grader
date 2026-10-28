#!/usr/bin/env python3
"""Read-only W201–W300 *selected source/test evidence* review, not 100 releases.

Bound to immutable protected-main Git blobs. AST reads test modules; it never
imports the subject files, executes legacy tests, starts services or writes.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

BASE = "6c78831bbb6e188717f86ef90243a836d2e0b67a"
V99_ORIGINAL = "d81711498eb05cfd84a007418cf389970b192197"
V291_REPAIR = "70938e4ce0a99f74dba481eb317bb82e7b917e13"
V291_SOURCE_PATH = "grading_accuracy_v99.py"
# Exact protected-main blobs: source of *current tests*, not original V-era
# executable release artifacts. Deliberately sparse: do not extrapolate.
CASES = {
    201: ("test_link_recovery_learning_v201.py", "1a1decf8623ef1570d33d5a64210808d28e85058",
          "standalone", ("main",)),
    209: ("test_information_lifecycle_archive_v209.py", "078967f12186728089677de253e492a96ea6c064",
          "unittest", ("test_event_is_current_through_fifth_day_and_archived_on_sixth",
                       "test_release_uses_the_same_five_day_policy")),
    211: ("test_verified_collection_neural_v211.py", "ab6c4e350f5fc74a01f79b0ae35cb161f592b3fd",
          "unittest", ("test_safety_contract_and_activation_threshold",
                       "test_less_than_1000_labels_never_activates")),
    262: ("test_tablet_gdrive_sync_perf_v262.py", "e78c5c4462d226276259e94014db677bab85ba5f",
          "unittest", ("test_pending_receipt_upload_failure_is_not_silently_ignored",
                       "test_success_completion_is_written_only_after_receipt_upload")),
    273: ("test_tablet_manifest_target_race_v273.py", "4560a0e3b3c49f661f751af59da53ff9e8440f7a",
          "unittest", ("test_runtime_passes_exact_manifest_sha_to_android_updater",
                       "test_invalid_manifest_sha_is_fail_closed")),
    291: ("test_card_core_crosscheck_v291.py", "e989f98223c5dc3ae20e95680d9bb51c6c5fef49",
          "unittest", ("test_python_grading_requires_all_three_defect_channels",
                       "test_browser_grading_matches_fail_closed_missing_evidence_contract")),
    299: ("test_card_regression_gate_v299.py", "281829e3f39f1e4c048203c1de0cd5cd4f2639de",
          "unittest", ("test_static_card_regressions_are_always_in_current_runtime",
                       "test_node_card_regressions_are_wired_without_forcing_node_on_tablet")),
    300: ("test_card_tablet_runtime_v300.py", "6ac6407c8f1883bbd31c36135a9f7f7181817331",
          "unittest", ("test_tablet_manifest_contains_complete_card_analysis_and_market_chain",
                       "test_missing_or_invalid_grade_evidence_stays_fail_closed")),
}
V99_MAIN_BLOB = "fa9ec562983813276d40d71674f0dd7bf7e456a6"
V99_JS_MAIN_BLOB = "1c607e86df23c6e07362a9dd7bc8aa3210fe5098"


def git(root: Path, *args: str) -> bytes:
    p = subprocess.run(["git", *args], cwd=root, capture_output=True,
                       check=False, timeout=40)
    if p.returncode:
        raise ValueError("git_forensic_unavailable:" + args[0])
    return p.stdout


def read_blob(root: Path, base: str, path: str, pinned: str) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{40}", base) or not re.fullmatch(r"[0-9a-f]{40}", pinned):
        raise ValueError("invalid_pinned_sha")
    if not isinstance(path, str) or not path or path.startswith("/") or ".." in path.split("/"):
        raise ValueError("invalid_pinned_path")
    entries = git(root, "ls-tree", "-z", base, "--", path).split(b"\0")
    if len(entries) != 2 or not entries[0]:
        raise ValueError("missing_original_test_file:" + path)
    meta, sep, filename = entries[0].partition(b"\t")
    if not sep or filename.decode("utf-8", "strict") != path:
        raise ValueError("wrong_git_tree_path")
    mode, kind, sha = meta.decode("ascii").split()
    if mode not in ("100644", "100755") or kind != "blob" or sha != pinned:
        raise ValueError("pinned_blob_changed:" + path)
    raw = git(root, "show", base + ":" + path)
    if len(raw) > 300_000:
        raise ValueError("oversized_historical_source")
    actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if actual != pinned:
        raise ValueError("git_content_not_matching_pinned_blob")
    return raw


def parse_methods(raw: bytes, *, name: str) -> set[str]:
    tree = ast.parse(raw.decode("utf-8", "strict"), filename=name)
    return {node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}


def inspect_evidence(data: dict[int, bytes], py: bytes, js: bytes,
                     original: bytes, repaired: bytes) -> dict[str, Any]:
    if set(data) != set(CASES):
        raise ValueError("incomplete_sampled_slice")
    reports = []
    for version in sorted(CASES):
        path, _sha, test_kind, required = CASES[version]
        raw = data[version]
        names = parse_methods(raw, name=path)
        if not set(required).issubset(names):
            raise ValueError("expected_historical_test_removed:v" + str(version))
        if test_kind == "standalone" and any(n.startswith("test_") for n in names):
            raise ValueError("standalone_test_reclassified")
        reports.append({
            "version": version,
            "path": path,
            "test_style": test_kind,
            "present_required_test_methods": list(required),
            "source_evidence": "PINNED_TEST_SOURCE_ONLY",
            "test_run": "NOT_EXECUTED_BY_FORENSIC_TOOL",
            "review_score": None,
        })
    s201 = data[201].decode("utf-8")
    if ("def main():" not in s201 or "_purchase_probe_with" not in s201
            or "urllib.request.build_opener =" not in s201):
        raise ValueError("v201_script_execution_boundary_not_detected")
    s209 = data[209].decode("utf-8")
    for term in ('dt.date(2026, 9, 10)', 'dt.date(2026, 9, 11)',
                 '"recently_ended"', '"archive"'):
        if term not in s209:
            raise ValueError("v209_five_day_contract_missing")
    s211 = data[211].decode("utf-8")
    if "MIN_INDEPENDENT_LABELS" not in s211 or "test_less_than_1000_labels_never_activates" not in s211:
        raise ValueError("v211_label_threshold_tests_missing")
    s262 = data[262].decode("utf-8")
    if "test_success_completion_is_written_only_after_receipt_upload" not in s262:
        raise ValueError("v262_success_receipt_guard_missing")
    s273 = data[273].decode("utf-8")
    if 'TCG_TARGET_MAIN_SHA' not in s273 or "test_invalid_manifest_sha_is_fail_closed" not in s273:
        raise ValueError("v273_pinned_target_test_missing")
    s291 = data[291].decode("utf-8")
    if "accuracy.combine_defect_risk(None, 0, 0)" not in s291:
        raise ValueError("v291_missing_channel_regression_missing")
    if "combine_defect_risk(-1" in s291 or "combineDefectRisk(-1" in s291:
        raise ValueError("v291_negative_gap_evidence_changed")
    s299 = data[299].decode("utf-8")
    for term in ("card_core_static_regressions", "card_core_node_regressions",
                 "test_card_core_crosscheck_v291.py"):
        if term not in s299:
            raise ValueError("v299_runtime_registration_guard_missing")
    s300 = data[300].decode("utf-8")
    if '"grading_accuracy_v99.js"' not in s300 or 'test_missing_or_invalid_grade_evidence_stays_fail_closed' not in s300:
        raise ValueError("v300_tablet_delivery_test_missing")
    original_text, fixed_text = original.decode("utf-8"), repaired.decode("utf-8")
    if "if x is not None:values.append(x*weight)" not in original_text:
        raise ValueError("not_original_v99_missing_evidence_behavior")
    if "if x is None:return 100" not in fixed_text or "if x is None:return 100" not in py.decode("utf-8"):
        raise ValueError("v291_fail_closed_successor_not_preserved")
    js_text = js.decode("utf-8")
    if ("if(!inputs.every(([value])=>finite(value)))return 100;" not in js_text
            or "return clamp(Math.max(" not in js_text):
        raise ValueError("v291_browser_contract_not_preserved")
    # This is a *verified test-coverage gap*, not proof of device behavior.
    # Both exact current-main functions lacked the negative-bound explicit guard.
    missing_negative_bounds = ("if x is None or x<0 or x>100" not in py.decode("utf-8")
                               and "Number(value)>=0&&Number(value)<=100" not in js_text)
    if not missing_negative_bounds:
        raise ValueError("pinned_main_negative_guard_changed_rebaseline_forensics")
    return {
        "schema": "tcg-w201-w300-selected-forensics/v1",
        "protected_main": BASE,
        "inspected_test_sources": len(reports),
        "inspected_numeric_versions": [r["version"] for r in reports],
        "test_source_rows": reports,
        "historical_v291_missing_evidence_repair": "EVIDENCED_IN_COMMIT_DIFF",
        "v201_probe": "STANDALONE_TEST_WITH_PATCHED_URLLIB_NOT_EXECUTED",
        "v209_event_release_lifecycle": "FIVE_DAY_BOUNDARY_ASSERTIONS_PRESENT_NOT_REEXECUTED",
        "v211_neural": "1000_LABEL_THRESHOLD_TEST_PRESENT_NOT_REEXECUTED",
        "v262_sync": "RECEIPT_BOUNDARY_TEST_PRESENT_NOT_REEXECUTED",
        "v273_tablet": "PINNED_SHA_RACE_REGRESSIONS_PRESENT_NOT_DEVICE_VERIFIED",
        "v291_v300": "GRADING_AND_RUNTIME_CONTRACT_TESTS_PRESENT_NOT_DEVICE_VERIFIED",
        "uncovered_negative_defect_bound_by_old_v291_tests": True,
        "current_main_python_js_negative_input_guard": "NOT_IMPLEMENTED_IN_PROTECTED_BASE",
        "related_candidate": "PR_903_DRAFT_HOLD_REQUIRES_WATCHED_SUCCESSOR",
        "complete_versions_reviewed": 0,
        "quality_score": None,
        "device": "DEVICE_UNVERIFIED",
        "status": "SELECTED_TEST_EVIDENCE_ONLY_REVIEW_INCOMPLETE",
    }


def inspect(root: Path) -> dict[str, Any]:
    root = root.resolve()
    git(root, "cat-file", "-e", BASE + "^{commit}")
    data = {v: read_blob(root, BASE, spec[0], spec[1]) for v, spec in CASES.items()}
    py = read_blob(root, BASE, V291_SOURCE_PATH, V99_MAIN_BLOB)
    js = read_blob(root, BASE, "grading_accuracy_v99.js", V99_JS_MAIN_BLOB)
    original = git(root, "show", V99_ORIGINAL + ":" + V291_SOURCE_PATH)
    repaired = git(root, "show", V291_REPAIR + ":" + V291_SOURCE_PATH)
    if git(root, "merge-base", V99_ORIGINAL, V291_REPAIR).strip() != V99_ORIGINAL.encode():
        raise ValueError("v291_not_successor_of_v99_original")
    return inspect_evidence(data, py, js, original, repaired)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    a = parser.parse_args()
    try:
        result = inspect(a.root)
    except (ValueError, OSError, UnicodeError, SyntaxError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc)[:180]}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only, pinned forensic slice of W001: V31 original, V99 and V100 records.

Never imports/runs historical application, starts a server, installs, or writes.
A source inconsistency is NOT a current device or current grading result.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
from pathlib import Path

ROOT_COMMIT = "6511c822f08685ab13ad3e2588d4bd093874c87b"
ORIGINAL_V99_IMPORT = "d81711498eb05cfd84a007418cf389970b192197"
V291_REPAIR_COMMIT = "70938e4ce0a99f74dba481eb317bb82e7b917e13"
PROTECTED_MAIN = "6c78831bbb6e188717f86ef90243a836d2e0b67a"
ROOT_SW_BLOB = "14c0e02000a8addb46baa592047b2ec5dfa5bc2c"
ROOT_UPDATER_BLOB = "42d432c933eef52a7d23325602f71bcd54e703d1"
ROOT_MANIFEST_BLOB = "a7bd26eb94520ff9f9c058a2cce5cbd38be54abd"
ROOT_REPORT_BLOB = "7113697f290141466fffccdfb07166439fe772ea"
ORIGINAL_V99_BLOB = "767d034edcf16c3fb1e0a4eba0c4520f5aa7a8a4"
V100_REPORT_BLOB = "efb22c305d62a5f84ae6959d09b3b7f2fbf827ea"
V100_PATH = "v100_reference/V100_FINAL_VERIFICATION_REPORT.json"


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True,
                            check=False, timeout=45)
    if result.returncode:
        raise ValueError("historical_git_evidence_unavailable:" + args[0])
    return result.stdout


def checked_object(root: Path, commit: str, path: str, expected_blob: str) -> bytes:
    rows = git(root, "ls-tree", "-z", commit, "--", path).split(b"\0")
    if len(rows) != 2 or not rows[0]:
        raise ValueError("missing_pinned_source:" + path)
    meta, sep, returned = rows[0].partition(b"\t")
    if not sep or returned.decode("utf-8", "strict") != path:
        raise ValueError("unexpected_pinned_path")
    mode, kind, blob = meta.decode("ascii").split()
    if kind != "blob" or mode not in ("100644", "100755") or blob != expected_blob:
        raise ValueError("pinned_historical_blob_changed:" + path)
    return git(root, "show", commit + ":" + path)


def root_tree(root: Path) -> set[str]:
    entries = git(root, "ls-tree", "-r", "-z", ROOT_COMMIT).split(b"\0")
    names: set[str] = set()
    for entry in entries:
        if not entry:
            continue
        meta, sep, raw_path = entry.partition(b"\t")
        if not sep or meta.decode("ascii").split()[1] != "blob":
            raise ValueError("unsafe_root_tree_object")
        names.add(raw_path.decode("utf-8", "strict"))
    return names


def icon_references(manifest: dict, serviceworker: str) -> tuple[list[str], list[str]]:
    if not isinstance(manifest, dict) or not isinstance(manifest.get("icons"), list):
        raise ValueError("malformed_root_manifest")
    icons = []
    for entry in manifest["icons"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("src"), str):
            raise ValueError("malformed_root_icon")
        icons.append(entry["src"].removeprefix("./"))
    match = re.search(r"\bconst\s+CORE\s*=\s*\[([^\]]+)\]", serviceworker)
    if not match or "cache.addAll(CORE)" not in serviceworker:
        raise ValueError("unrecognized_original_serviceworker")
    precache = [s.removeprefix("./") for s in re.findall(r"'(\.[^']+)'", match.group(1))]
    return icons, precache


def original_server_semantics(source: str) -> dict:
    """Classify exact early server structure without importing or running it."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError("invalid_historical_server_source") from exc
    root_functions = {
        node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)
    }
    handlers = [
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Handler"
    ]
    if len(handlers) != 1 or "collect" not in root_functions:
        raise ValueError("unrecognized_historical_server_handler")
    methods = {
        node.name: node for node in handlers[0].body
        if isinstance(node, ast.FunctionDef)
    }
    if not {"do_GET", "do_POST"}.issubset(methods):
        raise ValueError("unrecognized_historical_server_handler")

    def calls(node, name: str) -> bool:
        return any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == name
            for child in ast.walk(node)
        )

    def method_calls(node, name: str) -> bool:
        return any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == name
            for child in ast.walk(node)
        )

    def route_calls(method, route: str, call_name: str) -> bool:
        for branch in ast.walk(method):
            if not isinstance(branch, ast.If):
                continue
            if not any(
                isinstance(n, ast.Constant) and n.value == route
                for n in ast.walk(branch.test)
            ):
                continue
            if any(calls(statement, call_name) for statement in branch.body):
                return True
        return False

    on_get = methods["do_GET"]
    on_post = methods["do_POST"]
    # Both operations are observed in static code; a source path is not a
    # remotely reachable runtime proof. Pin the original Git blob separately.
    get_collect = route_calls(on_get, "/api/update", "collect")
    collector_writes = calls(root_functions["collect"], "save_db")
    post_applies = any(
        isinstance(node, ast.Constant) and node.value == "/api/apply"
        for node in ast.walk(on_post)
    ) and calls(on_post, "save_db")
    origin_guard = method_calls(on_post, "_require_mutation_origin")
    network_bind = any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        and n.func.id == "ThreadingHTTPServer"
        and n.args and isinstance(n.args[0], ast.Tuple)
        and n.args[0].elts and isinstance(n.args[0].elts[0], ast.Constant)
        and n.args[0].elts[0].value == "0.0.0.0"
        for n in ast.walk(tree)
    )
    if not (get_collect and collector_writes and post_applies and network_bind):
        raise ValueError("unrecognized_historical_server_flow")
    return {
        "historical_get_update_calls_collector": get_collect,
        "historical_collector_writes_database": collector_writes,
        "historical_post_apply_writes_database": post_applies,
        "historical_post_origin_guard_present": origin_guard,
        "historical_server_binds_all_interfaces": network_bind,
        "current_runtime_vulnerable_proven": False,
        "live_network_origin_replay_performed": False,
    }


def report_semantics(report: dict) -> dict:
    if not isinstance(report, dict):
        raise ValueError("invalid_v100_report")
    build = report.get("build")
    if not isinstance(build, str) or "v100" not in build.lower():
        raise ValueError("v100_build_label_missing")
    metrics = report.get("vision_self_learning")
    if not isinstance(metrics, dict) or not isinstance(metrics.get("metrics"), dict):
        raise ValueError("v100_metrics_absent")
    counts = metrics["metrics"].get("counts")
    if not isinstance(counts, dict):
        raise ValueError("v100_counts_missing")
    for name in ("tp", "tn", "fp", "fn"):
        if type(counts.get(name)) is not int or counts[name] < 0:
            raise ValueError("invalid_v100_count")
    limitations = report.get("limitations")
    if not isinstance(limitations, list) or not all(isinstance(v, str) for v in limitations):
        raise ValueError("v100_limitations_missing")
    passes = report.get("final_full_verification_passes")
    successful = report.get("successful_passes")
    if (not isinstance(passes, list) or type(successful) is not int
            or successful < 0 or successful != len(passes)):
        raise ValueError("v100_report_internal_pass_count_mismatch")
    # Count matching alone does not prove that pass records describe successful
    # verification. Reject duplicate/missing sequence numbers and failed rows.
    for number, row in enumerate(passes, start=1):
        if (not isinstance(row, dict)
                or type(row.get("pass")) is not int or row["pass"] != number
                or row.get("ok") is not True
                or not isinstance(row.get("tail"), str)
                or not row["tail"].strip()):
            raise ValueError("v100_report_pass_record_malformed")
    failed = report.get("failed_passes")
    if type(failed) is not int or failed != 0:
        raise ValueError("v100_report_failed_pass_count_inconsistent")
    if report.get("ok") is not True:
        raise ValueError("v100_report_success_flag_inconsistent")
    # An archived list of repeated PASS summaries is not six independently
    # identified executions. Preserve claims, but expose evidence limits.
    log_variants = len({row["tail"].strip() for row in passes})
    return {
        "build_label": build,
        "metadata_version": report.get("version"),
        "build_label_vs_metadata": "MISMATCH" if report.get("version") != 100 else "MATCH",
        "historical_record_passes": report["successful_passes"],
        "distinct_pass_log_texts": log_variants,
        "repeated_pass_log_texts": log_variants < len(passes),
        "independent_run_receipts_verified": False,
        "synthetic_positive_labels": counts["tp"],
        "synthetic_negative_labels": counts["tn"],
        "synthetic_false_positives": counts["fp"],
        "synthetic_false_negatives": counts["fn"],
        "calibration_adopted": metrics.get("calibration_adopted"),
        "explicit_real_photo_limitation": any(
            "synthetic" in v.lower() and "real" in v.lower() for v in limitations
        ),
        "real_photo_accuracy_verified": False,
    }


def inspect(root: Path) -> dict:
    root = root.resolve()
    head = git(root, "rev-parse", "--verify", "HEAD^{commit}").decode("ascii").strip()
    git(root, "merge-base", "--is-ancestor", ROOT_COMMIT, PROTECTED_MAIN)
    git(root, "merge-base", "--is-ancestor", ORIGINAL_V99_IMPORT, PROTECTED_MAIN)
    git(root, "merge-base", "--is-ancestor", V291_REPAIR_COMMIT, PROTECTED_MAIN)
    git(root, "merge-base", "--is-ancestor", PROTECTED_MAIN, head)
    if git(root, "rev-list", "--parents", "-n", "1", ROOT_COMMIT).decode().strip().split() != [ROOT_COMMIT]:
        raise ValueError("pinned_git_root_has_parents")
    root_files = root_tree(root)
    sw = checked_object(root, ROOT_COMMIT, "sw.js", ROOT_SW_BLOB).decode("utf-8")
    original_server = original_server_semantics(checked_object(
        root, ROOT_COMMIT, "tcg_updater.py", ROOT_UPDATER_BLOB).decode("utf-8"))
    manifest = json.loads(checked_object(root, ROOT_COMMIT, "manifest.webmanifest",
                                         ROOT_MANIFEST_BLOB))
    v31_report = json.loads(checked_object(
        root, ROOT_COMMIT,
        "v31_최종검증보고서.json",
        ROOT_REPORT_BLOB))
    icons, precache = icon_references(manifest, sw)
    missing_icons = sorted(set(icons) - root_files)
    missing_precache = sorted(set(p for p in precache if p not in ("", "./")) - root_files)
    v99_original = checked_object(root, ORIGINAL_V99_IMPORT,
                                  "grading_accuracy_v99.py", ORIGINAL_V99_BLOB).decode("utf-8")
    if "if x is not None:values.append(x*weight)" not in v99_original:
        raise ValueError("v99_original_behavior_not_recognized")
    v100 = json.loads(checked_object(root, ORIGINAL_V99_IMPORT, V100_PATH, V100_REPORT_BLOB))
    return {
        "schema": "tcg-historical-v31-v100-forensics/v1",
        "candidate_head": head,
        "protected_main": PROTECTED_MAIN,
        "original_root": ROOT_COMMIT,
        "original_root_file_count": len(root_files),
        "v31_original_server": original_server,
        "v31": {
            "status": "HISTORICAL_PACKAGE_GAP_EVIDENCED",
            "manifest_icon_references": icons,
            "missing_in_first_commit_icons": missing_icons,
            "missing_in_first_commit_serviceworker_precache": missing_precache,
            "serviceworker_precache_uses_add_all": True,
            "report_claims_icon_fix": any("아이콘" in x for x in v31_report.get("fixed", [])),
            "historical_impact": "root-only deploy would reject precache for absent assets",
            "current_runtime_regression_proven": False,
        },
        "v99": {
            "first_pinned_source_seen_at": ORIGINAL_V99_IMPORT,
            "source_blob": ORIGINAL_V99_BLOB,
            "original_skipped_missing_channel": True,
            "later_v291_repair_commit": V291_REPAIR_COMMIT,
            "complete_current_grading_review": False,
        },
        "v100": report_semantics(v100),
        "full_v1_v100_code_review": False,
        "quality_score": None,
        "device_verified": False,
        "status": "HISTORICAL_SOURCE_DISCREPANCY_REPRODUCED_REVIEW_PENDING",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        result = inspect(args.root)
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc)[:170]}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

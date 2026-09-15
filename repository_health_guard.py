#!/usr/bin/env python3
"""Fail-closed repository health audit for the production TCG collector.

The guard intentionally uses only the Python standard library so it can run on
GitHub Actions, Windows, and Termux without installing packages. It protects
production invariants and reports legacy workflow debt without automatically
rewriting source code.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
REPORT_PATH = ROOT / "REPOSITORY_HEALTH_REPORT.json"
EXPECTED_JOB_COUNT = 8
EXPECTED_TABLET_OUTPUT_COUNT = 17
LEGACY_7STEP_PATHS = (
    ".github/workflows/apply-android-7step-display.yml",
    ".github/workflows/apply-top-7step-ui.yml",
    "apply_android_7step_display_patch.py",
    "apply_top_7step_ui_patch.py",
)


def _read(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def _find_jobs(root: Path) -> tuple[int, list[str]]:
    path = root / "auto_update_all.py"
    if not path.is_file():
        raise RuntimeError("auto_update_all.py missing")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(isinstance(target, ast.Name) and target.id == "JOBS" for target in targets):
            continue
        value = ast.literal_eval(node.value)
        if not isinstance(value, (tuple, list)):
            raise RuntimeError("auto_update_all.JOBS must be a literal sequence")
        files: list[str] = []
        for row in value:
            if not isinstance(row, (tuple, list)) or len(row) < 3:
                raise RuntimeError("auto_update_all.JOBS row schema invalid")
            files.append(str(row[2]))
        return len(value), files
    raise RuntimeError("auto_update_all.JOBS assignment not found")


def _workflow_debt(root: Path) -> list[dict[str, str]]:
    workflow_dir = root / ".github" / "workflows"
    if not workflow_dir.is_dir():
        return []
    debt: list[dict[str, str]] = []
    for path in sorted(workflow_dir.glob("*.y*ml")):
        text = path.read_text(encoding="utf-8", errors="replace")
        compact = text.lower()
        if (
            path.name.startswith("apply-")
            and "workflow_dispatch" in compact
            and "contents: write" in compact
            and ("git push origin main" in compact or "git push" in compact)
        ):
            debt.append({
                "path": str(path.relative_to(root)).replace("\\", "/"),
                "reason": "manual apply workflow retains write/push behavior",
            })
    return debt


def _tablet_publish_controls(root: Path) -> dict[str, Any]:
    controls: dict[str, Any] = {}
    publisher_path = root / "tablet_collection_publish.py"
    test_path = root / "test_tablet_collection_publish.py"
    workflow_path = root / ".github" / "workflows" / "collection-verification-guard.yml"
    launcher_path = root / "TABLET_COLLECT_AND_SEND.sh"
    doc_path = root / "TABLET_COLLECTION_PUBLISH.md"

    controls["publisher_present"] = publisher_path.is_file()
    controls["regression_present"] = test_path.is_file()
    controls["launcher_present"] = launcher_path.is_file()
    controls["documentation_present"] = doc_path.is_file()
    controls["ci_workflow_present"] = workflow_path.is_file()

    if publisher_path.is_file():
        publisher = publisher_path.read_text(encoding="utf-8", errors="replace")
        match = re.search(r"OUTPUTS\s*=\s*tuple\('([^']+)'\.split\(\)\)", publisher)
        output_count = len(match.group(1).split()) if match else 0
        controls.update({
            "fixed_repository": "REPO = 'wlghks24/-tcg-grader'" in publisher,
            "public_output_count": output_count,
            "public_output_count_ok": output_count == EXPECTED_TABLET_OUTPUT_COUNT,
            "sha256_receipt": "hashlib.sha256(raw).hexdigest()" in publisher,
            "symlink_rejected": "path.is_symlink()" in publisher,
            "code_mixing_rejected": "changed <= set(OUTPUTS) | {RECEIPT}" in publisher,
            "post_commit_clean_check": "git(root, 'status', '--porcelain', '--', *OUTPUTS, RECEIPT)" in publisher,
            "receipt_freshness_bounded": "not -300 <= age <= 900" in publisher,
            "fail_on_degraded": "'--fail-on-degraded'" in publisher,
            "source_and_base_sha_bound": "data.get('source_sha') != base" in publisher and "data.get('base_sha') != base" in publisher,
            "latest_main_before_publish": "if publish and source != base" in publisher,
            "latest_main_after_collection": "if git(root, 'rev-parse', 'FETCH_HEAD') != base" in publisher,
            "isolated_worktree": "'worktree', 'add', '--detach'" in publisher,
            "persistent_run_evidence": "'.local' / 'state' / 'tcg-grader' / 'collection-runs'" in publisher,
            "pr_only_delivery": "'gh', 'pr', 'create'" in publisher and "'gh', 'pr', 'merge'" not in publisher,
        })
        push_pos = publisher.find("git(work, 'push'")
        verify_pos = publisher.find("verify_receipt(work, base)")
        controls["verify_before_push"] = verify_pos >= 0 and push_pos >= 0 and verify_pos < push_pos
    else:
        controls["public_output_count"] = 0
        controls["public_output_count_ok"] = False

    if workflow_path.is_file():
        workflow = workflow_path.read_text(encoding="utf-8", errors="replace")
        controls.update({
            "ci_receipt_trigger": "'tablet_collection_receipt.json'" in workflow,
            "ci_snapshot_verification": "tablet_collection_publish.py --verify-base" in workflow,
            "ci_full_history_for_base_diff": "fetch-depth: 0" in workflow,
            "ci_does_not_replace_snapshot": "Verify tablet snapshot without replacing it with cloud collection" in workflow,
        })

    if test_path.is_file():
        tests = test_path.read_text(encoding="utf-8", errors="replace")
        controls.update({
            "tamper_regression": "test_committed_bytes_cannot_be_replaced_before_validation" in tests,
            "code_mixing_regression": "failure == 'code'" in tests,
            "failed_gate_blocks_push_regression": "test_failed_collection_gate_never_pushes" in tests,
            "symlink_regression": "test_symlink_not_uploaded" in tests,
        })

    return controls


def audit(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    blockers: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    checks: dict[str, Any] = {}

    legacy_present = [path for path in LEGACY_7STEP_PATHS if (root / path).exists()]
    checks["legacy_7step_removed"] = not legacy_present
    if legacy_present:
        blockers.append({
            "code": "LEGACY_7STEP_MUTATOR_PRESENT",
            "detail": ", ".join(legacy_present),
        })

    try:
        job_count, job_files = _find_jobs(root)
        checks["collection_jobs"] = {"count": job_count, "files": job_files}
        if job_count != EXPECTED_JOB_COUNT:
            blockers.append({
                "code": "COLLECTION_JOB_COUNT_DRIFT",
                "detail": f"expected {EXPECTED_JOB_COUNT}, found {job_count}",
            })
        if len(set(job_files)) != len(job_files):
            blockers.append({
                "code": "COLLECTION_OUTPUT_DUPLICATE",
                "detail": "auto_update_all.JOBS contains duplicate output files",
            })
    except (OSError, SyntaxError, ValueError, RuntimeError) as exc:
        checks["collection_jobs"] = {"error": str(exc)}
        blockers.append({"code": "COLLECTION_JOB_SSoT_UNREADABLE", "detail": str(exc)})

    refresh_path = ".github/workflows/tcg-static-data-refresh.yml"
    try:
        refresh = _read(root, refresh_path)
        perf = {
            "concurrency_group": "concurrency:" in refresh and "group:" in refresh,
            "cancel_in_progress": "cancel-in-progress: true" in refresh,
            "job_timeout": "timeout-minutes:" in refresh,
            "discard_stale_main_snapshot": "main advanced during collection; discard this snapshot" in refresh,
            "commit_only_when_changed": "git diff --cached --quiet" in refresh,
        }
        checks["static_refresh_performance_controls"] = perf
        missing = [name for name, ok in perf.items() if not ok]
        if missing:
            blockers.append({
                "code": "STATIC_REFRESH_PERFORMANCE_GUARD_MISSING",
                "detail": ", ".join(missing),
            })
    except OSError as exc:
        checks["static_refresh_performance_controls"] = {"error": str(exc)}
        blockers.append({"code": "STATIC_REFRESH_WORKFLOW_MISSING", "detail": str(exc)})

    try:
        updater = _read(root, "auto_update_all.py")
        runtime_perf = {
            "bounded_worker_policy": "def _worker_count(" in updater,
            "parallel_executor": "ThreadPoolExecutor" in updater,
            "adaptive_timeout": "def _job_timeout(" in updater,
            "managed_process_tree": "def _run_managed_process(" in updater,
            "atomic_runtime_import": "atomic_write_" in updater,
        }
        checks["collector_runtime_performance_controls"] = runtime_perf
        missing = [name for name, ok in runtime_perf.items() if not ok]
        if missing:
            blockers.append({
                "code": "COLLECTOR_PERFORMANCE_CONTROL_MISSING",
                "detail": ", ".join(missing),
            })
    except OSError as exc:
        blockers.append({"code": "COLLECTOR_RUNTIME_MISSING", "detail": str(exc)})

    tablet = _tablet_publish_controls(root)
    checks["tablet_publish_controls"] = tablet
    required_tablet = (
        "publisher_present", "regression_present", "launcher_present", "documentation_present", "ci_workflow_present",
        "fixed_repository", "public_output_count_ok", "sha256_receipt", "symlink_rejected", "code_mixing_rejected",
        "post_commit_clean_check", "receipt_freshness_bounded", "fail_on_degraded", "source_and_base_sha_bound",
        "latest_main_before_publish", "latest_main_after_collection", "isolated_worktree", "persistent_run_evidence",
        "pr_only_delivery", "verify_before_push", "ci_receipt_trigger", "ci_snapshot_verification",
        "ci_full_history_for_base_diff", "ci_does_not_replace_snapshot", "tamper_regression",
        "code_mixing_regression", "failed_gate_blocks_push_regression", "symlink_regression",
    )
    missing_tablet = [name for name in required_tablet if tablet.get(name) is not True]
    if missing_tablet:
        blockers.append({
            "code": "TABLET_PUBLISH_CONTROL_MISSING",
            "detail": ", ".join(missing_tablet),
        })

    debt = _workflow_debt(root)
    checks["manual_apply_workflow_debt"] = {
        "count": len(debt),
        "items": debt[:100],
        "policy": "report-only; remove only after feature is confirmed integrated",
    }
    if debt:
        warnings.append({
            "code": "MANUAL_APPLY_WORKFLOW_DEBT",
            "detail": f"{len(debt)} write-capable apply workflow(s) remain; review incrementally",
        })

    report = {
        "schema_version": 2,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "root": str(root),
        "status": "PASS" if not blockers else "BLOCKED",
        "summary": {
            "blockers": len(blockers),
            "warnings": len(warnings),
            "expected_collection_jobs": EXPECTED_JOB_COUNT,
            "expected_tablet_outputs": EXPECTED_TABLET_OUTPUT_COUNT,
        },
        "checks": checks,
        "blockers": blockers,
        "warnings": warnings,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--no-fail", action="store_true", help="write diagnostics without returning a failing status")
    args = parser.parse_args()

    report = audit(args.root)
    destination = args.report
    if not destination.is_absolute():
        destination = args.root / destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    if report["warnings"]:
        for row in report["warnings"]:
            print(f"WARNING {row['code']}: {row['detail']}")
    if report["blockers"]:
        for row in report["blockers"]:
            print(f"BLOCKER {row['code']}: {row['detail']}")
    return 0 if args.no_fail or report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

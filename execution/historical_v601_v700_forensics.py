#!/usr/bin/env python3
"""Selected V601–V700 protected-main evidence proof, not a 100-version review.

Only read original Git blobs and inherited JSON evidence. Never import/execute
TCG app sources, dispatch jobs, contact devices, update grades or write state.
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
PARENT_MAIN = "execution/evidence/version_review_findings_v001_v879.json"
PARENT_MAIN_BLOB = "d2347527056b5b8ec06a9774df50f216219dfa10"
PARENT_W401 = "execution/evidence/W401_V413_V489_FINDINGS_DELTA.json"
PARENT_W401_BLOB = "d15da1cddedfdc56fe17bdc40b37b5cd7b91228f"
PARENT_W501 = "execution/evidence/W501_V503_V599_FINDINGS_DELTA.json"
PARENT_W501_BLOB = "238f2b193488b40e12057d88a1a7642359eed563"
DELTA = "execution/evidence/W601_V619_V664_FINDINGS_DELTA.json"
SCHEMA = "tcg-w601-selective-finding-delta/v1"
PINNED = {
    "execution/tests/test_free_only_ai_code_improver_v619.py": "a37f6a6740f6ebc3df47e6d814e9f798f95d6660",
    ".github/tablet-autonomy/feature_catalog_successor_v645.json": "7bfc763bad17427e8b059a5fba11289be3404a61",
    ".github/tablet-autonomy/feature_catalog_successor_v646.json": "a53d3725aae508f5e4efc54007032fcebc62eade",
    "execution/tests/test_tablet_successor_v646.py": "f7a6b0ccd54e29b8646c578c44a9ae31e713492d",
    "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v646.json": "8b3c4eb280c92941472c5c982eaf18ce08da523b",
    ".github/tablet-autonomy/workspace_evidence_successor_v653.json": "e25535009d16dd36634d8de494e5f825084888dc",
    "execution/tests/test_learning_scan_budget_v657.py": "bce6be9c44bc857b3f5eb8778fc2c96e602d6a01",
    ".github/tablet-autonomy/image_autonomy_successor_v661.json": "2744ebbe9c1012f7631ed43a82949cc75ba6d3d6",
    "execution/tests/test_image_autonomy_v661.py": "9aea00523f01f1093cd174553fbd10f587425fff",
    ".github/tablet-autonomy/image_worker_isolation_successor_v664.json": "ad0d461dcdc1ced5cd817b9ce96ad420e7a7248d",
    "execution/tests/test_image_worker_isolation_v664.py": "57736a4f94d8d06ede1957c49cb3b5d1cbf90d44",
}
VERSION_SCOPE = [619, 645, 646, 653, 657, 661, 664]
SHA1 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def git(root: Path, *args: str) -> bytes:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True,
                          timeout=45, check=False)
    if proc.returncode:
        raise ValueError("git_read_failed:" + (args[0] if args else "unknown"))
    return proc.stdout


def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, val in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = val
    return result


def parse(raw: bytes) -> dict[str, Any]:
    if len(raw) > 500_000:
        raise ValueError("oversized_evidence")
    result = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                        parse_constant=lambda _: (_ for _ in ()).throw(
                            ValueError("nonfinite_evidence")))
    if not isinstance(result, dict):
        raise ValueError("evidence_not_object")
    return result


def read_object(root: Path, commit: str, path: str, blob: str) -> bytes:
    if not SHA1.fullmatch(commit) or not SHA1.fullmatch(blob):
        raise ValueError("invalid_git_pin")
    actual = git(root, "rev-parse", "--verify", f"{commit}:{path}").decode("ascii").strip()
    if actual != blob:
        raise ValueError("original_git_blob_drift:" + path)
    raw = git(root, "show", f"{commit}:{path}")
    if hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest() != blob:
        raise ValueError("corrupt_git_blob")
    return raw


def review(root: Path) -> dict[str, Any]:
    root = root.resolve()
    git(root, "rev-parse", "--verify", BASE + "^{commit}")
    originals = {path: read_object(root, BASE, path, digest)
                 for path, digest in PINNED.items()}
    tests: dict[str, list[str]] = {}
    proofs: dict[str, dict[str, Any]] = {}
    for path, raw in originals.items():
        if path.endswith(".py"):
            tree = ast.parse(raw, filename=path)
            tests[path] = [node.name for node in ast.walk(tree)
                           if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                           and node.name.startswith("test_")]
        elif path.endswith(".json") and "successor" in path:
            data = parse(raw)
            reviewed = data.get("reviewed_sha256")
            if not isinstance(reviewed, dict) or not reviewed:
                raise ValueError("missing_reviewed_source_pins:" + path)
            if any(value is not None and
                   (not isinstance(value, str) or SHA256.fullmatch(value) is None)
                   for value in reviewed.values()):
                raise ValueError("invalid_reviewed_sha256:" + path)
            if data.get("physical_tablet_runtime_verified") is not False:
                raise ValueError("unverified_device_claim:" + path)
            if data.get("deployment_allowed") is not False:
                raise ValueError("unexpected_successor_deploy_allowed:" + path)
            for field in ("base_commit", "candidate_commit"):
                commit = data.get(field)
                if not isinstance(commit, str) or SHA1.fullmatch(commit) is None:
                    raise ValueError("invalid_successor_commit:" + path)
                # Original candidate must exist within the protected main Git ancestry.
                git(root, "merge-base", "--is-ancestor", commit, BASE)
            proofs[path] = {"schema": data.get("schema"),
                            "reviewed_sha256_count": len(reviewed),
                            "device_verified": False, "deployment_allowed": False}
    receipt = parse(originals["TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v646.json"])
    if receipt.get("verification", {}).get("physical_tablet_runtime_verified") is not False:
        raise ValueError("receipt_device_claim_inconsistent")
    if "ImproverTests" not in originals[
        "execution/tests/test_free_only_ai_code_improver_v619.py"].decode("utf-8"):
        raise ValueError("v619_registration_missing")
    if not any("test_one_label_scan" in x for x in tests[
        "execution/tests/test_learning_scan_budget_v657.py"]):
        raise ValueError("v657_cached_learning_assertion_missing")
    if not any("test_missing_labels" in x for x in tests[
        "execution/tests/test_image_autonomy_v661.py"]):
        raise ValueError("v661_missing_labels_gate_unregistered")
    if not any("test_malformed_real_challenger" in x for x in tests[
        "execution/tests/test_image_worker_isolation_v664.py"]):
        raise ValueError("v664_worker_guard_unregistered")
    parents = [(PARENT_MAIN, PARENT_MAIN_BLOB), (PARENT_W401, PARENT_W401_BLOB),
               (PARENT_W501, PARENT_W501_BLOB)]
    head = git(root, "rev-parse", "--verify", "HEAD^{commit}").decode("ascii").strip()
    for path, sha in parents:
        read_object(root, head, path, sha)
    parent = parse(git(root, "show", "HEAD:" + PARENT_MAIN))
    w401 = parse(git(root, "show", "HEAD:" + PARENT_W401))
    w501 = parse(git(root, "show", "HEAD:" + PARENT_W501))
    data = parse(git(root, "show", "HEAD:" + DELTA))
    if data.get("schema") != SCHEMA or data.get("baseline_main_sha") != BASE:
        raise ValueError("wrong_w601_delta_schema_or_main")
    if data.get("inherited_finding_count") != (len(parent.get("findings", []))
                                                + len(w401.get("findings", []))
                                                + len(w501.get("findings", []))):
        raise ValueError("broken_parent_finding_count")
    if data.get("inherited_finding_count") != 31:
        raise ValueError("unexpected_parent_finding_count")
    if (data.get("parent_main_ledger_blob") != PARENT_MAIN_BLOB or
            data.get("parent_w401_delta_blob") != PARENT_W401_BLOB or
            data.get("parent_w501_delta_blob") != PARENT_W501_BLOB):
        raise ValueError("delta_parent_pin_mismatch")
    findings = data.get("findings")
    if not isinstance(findings, list) or len(findings) != 7:
        raise ValueError("missing_seven_scoped_findings")
    if [row.get("id") for row in findings] != [f"W601-F{n:03d}" for n in range(1, 8)]:
        raise ValueError("wrong_scoped_finding_sequence")
    for finding in findings:
        if (finding.get("version") not in VERSION_SCOPE
                or finding.get("quality_score") is not None
                or finding.get("state") != "EVIDENCE_GAP_NOT_A_PROVEN_RUNTIME_DEFECT"):
            raise ValueError("false_completion_or_unanchored_version")
    if (data.get("reviewed_version_ids") != VERSION_SCOPE
            or data.get("entire_window_fully_reviewed") is not False
            or data.get("grading_quality_score") is not None
            or data.get("physical_tablet_verified") is not False):
        raise ValueError("false_w601_completion_claim")
    return {"schema": SCHEMA, "baseline_main_sha": BASE,
            "selected_source_test_blobs": [{"path": path, "blob": PINNED[path]}
                                          for path in sorted(PINNED)],
            "selected_version_ids": VERSION_SCOPE,
            "test_function_names": tests, "proof_summaries": proofs,
            "inherited_finding_count": data["inherited_finding_count"],
            "new_finding_count": len(findings),
            "total_carried_finding_count": 31 + len(findings),
            "all_100_versions_reviewed": False,
            "current_head_target_tests_executed": False,
            "quality_score": None,
            "physical_tablet_verified": False,
            "status": "SELECTED_PROVENANCE_ONLY_HOLD"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        result = review(args.root)
    except (OSError, UnicodeError, ValueError, SyntaxError,
            subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc)[:160]}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

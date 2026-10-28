#!/usr/bin/env python3
"""Strict evidence-coverage matrix for V1–Vcurrent; NOT a version quality certification.

Consumes existing SHA-linked V100 inventory checkpoints. Reports missing REVIEW
evidence rather than confusing filename/commit tokens with tested releases.
No network, device operations, tracked-file writes, or runtime module imports.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

from version_window_audit import SCHEMA as SOURCE_SCHEMA, canonical_sha256

MATRIX_SCHEMA = "tcg-version-evidence-matrix/v1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
STATUS = "INVENTORY_ONLY_NOT_RELEASE_VERIFIED"


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("duplicate_json_key")
        result[name] = value
    return result


def _parse_file(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_000_000:
        raise ValueError("unsafe_window_checkpoint")
    data = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=_unique,
        parse_constant=lambda v: (_ for _ in ()).throw(ValueError("non_finite_json")),
    )
    if not isinstance(data, dict):
        raise ValueError("window_payload_not_object")
    return data


def _tokens(row: dict[str, Any], first: int, last: int) -> list[int]:
    tokens = row.get("tokens")
    if (not isinstance(tokens, list) or not tokens
            or any(type(n) is not int or not first <= n <= last for n in tokens)
            or tokens != sorted(set(tokens))):
        raise ValueError("invalid_version_hint_tokens")
    return tokens


def _validate(window: dict[str, Any], first: int, expected_head: str,
              prior: str | None) -> None:
    if window.get("schema") != SOURCE_SCHEMA:
        raise ValueError("wrong_inventory_schema")
    if window.get("window") != {"start": first, "end": first + 99}:
        raise ValueError("wrong_window_bounds")
    src = window.get("source")
    if not isinstance(src, dict) or src.get("head") != expected_head:
        raise ValueError("source_head_mismatch")
    if src.get("is_shallow") is not False or src.get("history_limited") is not False:
        raise ValueError("incomplete_git_history")
    if window.get("previous_checkpoint_sha256") != prior:
        raise ValueError("broken_predecessor_link")
    digest = window.get("checkpoint_sha256")
    if not isinstance(digest, str) or SHA64.fullmatch(digest) is None:
        raise ValueError("invalid_checkpoint_sha")
    if digest != canonical_sha256(window):
        raise ValueError("checkpoint_digest_mismatch")
    if (window.get("status") != STATUS or window.get("tests") != "NOT_RUN"
            or window.get("device") != "DEVICE_UNVERIFIED"
            or window.get("score") is not None):
        raise ValueError("unsupported_claim_of_verification")
    if not isinstance(window.get("path_hints"), list):
        raise ValueError("missing_path_hints")
    if not isinstance(window.get("commit_subject_hints"), list):
        raise ValueError("missing_commit_hints")
    union: set[int] = set()
    paths: set[str] = set()
    for row in window["path_hints"]:
        if not isinstance(row, dict):
            raise ValueError("malformed_path_hint")
        path, blob = row.get("path"), row.get("git_blob")
        if (not isinstance(path, str) or not path or path in paths
                or not isinstance(blob, str) or SHA40.fullmatch(blob) is None
                or row.get("classification") != "filename_hint_only"):
            raise ValueError("invalid_path_hint")
        paths.add(path)
        union.update(_tokens(row, first, first + 99))
    commits: set[str] = set()
    for row in window["commit_subject_hints"]:
        if not isinstance(row, dict):
            raise ValueError("malformed_commit_hint")
        commit = row.get("commit")
        if (not isinstance(commit, str) or SHA40.fullmatch(commit) is None
                or commit in commits or not isinstance(row.get("subject"), str)
                or row.get("classification") != "commit_subject_hint_only"):
            raise ValueError("invalid_commit_hint")
        commits.add(commit)
        union.update(_tokens(row, first, first + 99))
    candidates = window.get("candidate_version_tokens")
    if candidates != sorted(union):
        raise ValueError("candidate_tokens_not_supported")
    # Parent inventory explicitly labels unrepresented version numbers as
    # unverified evidence gaps, NEVER missing software releases.
    truth = window.get("coverage_truth")
    if not isinstance(truth, dict):
        raise ValueError("missing_parent_audit_truth")
    if (truth.get("version_slots") != 100
            or truth.get("matched_version_token_hints") != len(candidates)
            or truth.get("unrepresented_number_hints")
            != [v for v in range(first, first + 100) if v not in union]
            or truth.get("classification") != "AUDIT_NOT_DONE_NOT_A_RELEASE_PASS"
            or truth.get("version_by_version_source_review_performed") is not False
            or truth.get("version_by_version_regressions_executed") is not False
            or truth.get("version_quality_score") is not None):
        raise ValueError("false_coverage_or_review_claim")
    for name in ("excluded_cross_project_paths", "unsafe_versioned_paths"):
        val = window.get(name)
        if type(val) is not int or val < 0:
            raise ValueError("invalid_inventory_count")


def _path_kind(path: str) -> str:
    filename = path.rsplit("/", 1)[-1].lower()
    if (filename.startswith(("test_", "verify_", "verification_"))
            or "/tests/" in path.lower()):
        return "test_filename_hint"
    if ("report" in filename or filename.endswith((".md", ".txt"))):
        return "historical_document_hint"
    return "source_filename_hint"


def build(checkpoint_dir: Path, *, end_version: int, expected_head: str) -> dict[str, Any]:
    if type(end_version) is not int or not 1 <= end_version <= 9999:
        raise ValueError("invalid_last_version")
    if not isinstance(expected_head, str) or SHA40.fullmatch(expected_head) is None:
        raise ValueError("invalid_expected_head")
    last_windows = range(1, end_version + 1, 100)
    findings: dict[int, dict[str, Any]] = defaultdict(lambda: {
        "source_filename_hints": [], "test_filename_hints": [],
        "document_filename_hints": [], "commit_subject_hints": [],
    })
    windows: list[dict[str, Any]] = []
    prior = None
    for first in last_windows:
        path = checkpoint_dir / f"window_v{first:03d}_v{first+99:03d}.json"
        data = _parse_file(path)
        _validate(data, first, expected_head, prior)
        prior = data["checkpoint_sha256"]
        for row in data["path_hints"]:
            kind = _path_kind(row["path"])
            key = {
                "source_filename_hint": "source_filename_hints",
                "test_filename_hint": "test_filename_hints",
                "historical_document_hint": "document_filename_hints",
            }[kind]
            for v in row["tokens"]:
                if v <= end_version:
                    findings[v][key].append(row["path"])
        for row in data["commit_subject_hints"]:
            for v in row["tokens"]:
                if v <= end_version:
                    findings[v]["commit_subject_hints"].append(row["commit"])
        windows.append({
            "first": first, "last": min(first + 99, end_version),
            "checkpoint_sha256": prior,
            "raw_filename_hints": len(data["path_hints"]),
            "raw_commit_subject_hints": len(data["commit_subject_hints"]),
            "excluded_cross_project_paths": data["excluded_cross_project_paths"],
        })
    rows = []
    for version in range(1, end_version + 1):
        evidence = findings[version]
        has_hint = any(evidence.values())
        rows.append({
            "version": version,
            "window_start": ((version - 1) // 100) * 100 + 1,
            **{key: sorted(set(values)) for key, values in evidence.items()},
            "evidence_state": "LEADS_ONLY_NOT_REVIEWED" if has_hint else "NO_MAIN_TOKEN_LEAD",
            "source_code_review": "NOT_PERFORMED",
            "error_typo_omission_review": "NOT_PERFORMED",
            "current_head_behavior_tests": "NOT_VERIFIED",
            "lineage_and_patch_review": "NOT_PERFORMED",
            "quality_score": None,
            "deployment": "HOLD_DEVICE_UNVERIFIED",
        })
    counts = []
    for window in windows:
        group = [v for v in rows if window["first"] <= v["version"] <= window["last"]]
        counts.append({
            **window,
            "numeric_slots": len(group),
            "slots_with_main_token_lead": sum(v["evidence_state"] == "LEADS_ONLY_NOT_REVIEWED" for v in group),
            "slots_without_main_token_lead": sum(v["evidence_state"] == "NO_MAIN_TOKEN_LEAD" for v in group),
            "individually_completed_code_reviews": 0,
            "verifiable_quality_scores": 0,
            "result": "NOT_AUDITED",
        })
    return {
        "schema": MATRIX_SCHEMA,
        "source_head": expected_head,
        "latest_requested_version": end_version,
        "scope": "main_branch_file_and_commit_subject_leads_only",
        "window_reviews": counts,
        "version_reviews": rows,
        "carry_forward_hash": prior,
        "reviewed_versions": 0,
        "quality_score": None,
        "status": "EVIDENCE_GAPS_REMAIN_NO_RELEASE_APPROVAL",
        "physical_tablet_verified": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--checkpoint-dir", type=Path, required=True)
    ap.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--end-version", type=int, default=879)
    ap.add_argument("--source-sha", required=True,
                    help="Exact immutable protected-main SHA, never audit branch HEAD")
    args = ap.parse_args()
    try:
        if SHA40.fullmatch(args.source_sha) is None:
            raise ValueError("source_must_be_full_protected_sha")
        head = subprocess.run(
            ["git", "rev-parse", "--verify", args.source_sha + "^{commit}"],
            cwd=args.repo_root.resolve(), capture_output=True, text=True, check=True, timeout=30,
        ).stdout.strip()
        payload = build(args.checkpoint_dir, end_version=args.end_version,
                        expected_head=head)
    except (ValueError, OSError, UnicodeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc)[:180]}))
        return 2
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

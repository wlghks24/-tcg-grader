#!/usr/bin/env python3
"""Validate and carry a *subset* of reviewed findings across V100 windows.

Verifies exact protected-main Git blobs and commit ancestry; never interprets
a proposed patch/test success as merged, deployed, or a whole-version score.
Local Git reads only; no network and no runtime import.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

SCHEMA = "tcg-version-scoped-findings/v1"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
FINDING = re.compile(r"^W(\d{3})-F\d{3}$")
CLOSED = {"HISTORICAL_REPAIR_EVIDENCED"}
STATES = CLOSED | {
    "PATCH_CANDIDATE_BLOCKED", "OPEN_SUCCESSOR_REQUIRED",
    "OPEN_LINEAGE_GUARD", "OPEN_HISTORICAL_EXECUTION_UNSAFE",
    "PROVENANCE_NOT_VERIFIED", "DRAFT_NOT_MERGED",
}
SEVERITIES = {"P0", "P1", "P2"}


def read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 300_000:
        raise ValueError("unsafe_findings_source")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("duplicate_findings_json_key")
            out[key] = value
        return out
    data = json.loads(path.read_text("utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda _n: (_ for _ in ()).throw(
                          ValueError("non_finite_findings_value")))
    if not isinstance(data, dict):
        raise ValueError("bad_findings_schema")
    return data


def git(root: Path, *args: str) -> bytes:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True,
                          check=False, timeout=45)
    if proc.returncode:
        raise ValueError("git_evidence_unavailable:" + (args[0] if args else ""))
    return proc.stdout


def baseline_blob(root: Path, base: str, path: str) -> str:
    if (not isinstance(path, str) or not path or path.startswith("/")
            or ".." in path.split("/") or "\\" in path or "\0" in path):
        raise ValueError("unsafe_evidence_path")
    data = git(root, "ls-tree", "-z", base, "--", path).split(b"\0")
    if len(data) != 2 or not data[0]:
        raise ValueError("baseline_file_not_found")
    meta, sep, name = data[0].partition(b"\t")
    if not sep or name.decode("utf-8") != path:
        raise ValueError("baseline_evidence_not_exact")
    mode, kind, blob = meta.decode("ascii").split()
    if mode not in ("100644", "100755") or kind != "blob":
        raise ValueError("unsafe_baseline_source_type")
    return blob


def validate(ledger: dict[str, Any], root: Path, *, head: str,
             latest: int = 879) -> dict[str, Any]:
    if ledger.get("schema") != SCHEMA:
        raise ValueError("bad_findings_schema")
    base = ledger.get("baseline_main_sha")
    if not isinstance(base, str) or HEX40.fullmatch(base) is None:
        raise ValueError("invalid_baseline_sha")
    if not isinstance(head, str) or HEX40.fullmatch(head) is None:
        raise ValueError("invalid_candidate_head")
    if type(latest) is not int or not 1 <= latest <= 9999:
        raise ValueError("invalid_latest")
    git(root, "merge-base", "--is-ancestor", base, head)
    if ledger.get("scope") != "selected_confirmed_or_pending_findings_only_not_complete_879_review":
        raise ValueError("scope_must_be_partial")
    findings = ledger.get("findings")
    if not isinstance(findings, list) or not findings or len(findings) > 1500:
        raise ValueError("bad_findings_list")
    ids = set()
    window = []
    for v in range(1, latest+1, 100):
        window.append({"first": v, "last": min(v+99,latest),
                       "open_carry_forward_ids": [],
                       "historical_repair_record_ids": [],
                       "quality_score": None,
                       "device": "DEVICE_UNVERIFIED"})
    for row in findings:
        if not isinstance(row, dict):
            raise ValueError("bad_finding_record")
        fid = row.get("id")
        match = FINDING.fullmatch(fid) if isinstance(fid, str) else None
        first = row.get("first_observed_version")
        if (not match or fid in ids or type(first) is not int or not 1 <= first <= latest
                or int(match.group(1)) != ((first-1)//100)*100+1):
            raise ValueError("invalid_or_duplicate_finding_id")
        ids.add(fid)
        versions = row.get("related_versions")
        if (not isinstance(versions,list) or not versions
                or any(type(x) is not int or not 1 <= x <= latest for x in versions)
                or versions != sorted(set(versions)) or first not in versions):
            raise ValueError("invalid_related_versions")
        if row.get("severity") not in SEVERITIES or row.get("state") not in STATES:
            raise ValueError("invalid_finding_state")
        if (row.get("quality_score") is not None
                or row.get("physical_tablet_verified") is not False):
            raise ValueError("unsupported_quality_or_device_claim")
        if not isinstance(row.get("summary"), str) or len(row["summary"]) < 18:
            raise ValueError("missing_finding_summary")
        if not isinstance(row.get("note"), str) or not row["note"]:
            raise ValueError("missing_finding_note")
        pr = row.get("candidate_pr")
        if pr is not None and (type(pr) is not int or pr < 1):
            raise ValueError("invalid_candidate_pr")
        if row["state"] == "PATCH_CANDIDATE_BLOCKED" and pr is None:
            raise ValueError("blocked_candidate_without_pr")
        # Never mark an old defect repaired until its actual repair version.
        resolution = row.get("historical_resolution_version")
        if row["state"] in CLOSED:
            if (type(resolution) is not int or resolution < first
                    or resolution > latest or resolution not in versions):
                raise ValueError("historical_resolution_version_required")
        elif resolution is not None:
            raise ValueError("unreviewed_resolution_claim")
        refs = row.get("source_refs")
        if not isinstance(refs, list) or len(refs)>16:
            raise ValueError("invalid_source_refs")
        if row["state"] in CLOSED | {"PATCH_CANDIDATE_BLOCKED","OPEN_SUCCESSOR_REQUIRED",
                                     "OPEN_LINEAGE_GUARD", "OPEN_HISTORICAL_EXECUTION_UNSAFE"} and not refs:
            raise ValueError("missing_source_anchors")
        seen = set()
        for item in refs:
            if not isinstance(item, dict) or set(item) != {"path","blob"}:
                raise ValueError("malformed_source_reference")
            path, blob = item["path"], item["blob"]
            if path in seen or not isinstance(blob,str) or HEX40.fullmatch(blob) is None:
                raise ValueError("invalid_source_blob_reference")
            seen.add(path)
            if baseline_blob(root,base,path)!=blob:
                raise ValueError("baseline_source_blob_changed:" + path)
        commits = row.get("code_history")
        if not isinstance(commits,list) or len(commits)>15 or len(commits)!=len(set(commits)):
            raise ValueError("invalid_history_commits")
        for sha in commits:
            if not isinstance(sha,str) or HEX40.fullmatch(sha) is None:
                raise ValueError("invalid_history_commit_sha")
            git(root, "cat-file", "-e", sha+"^{commit}")
            git(root, "merge-base", "--is-ancestor", sha, base)
        tests=row.get("tests")
        if not isinstance(tests,list) or len(tests)>30 or any(
                not isinstance(x,str) or not x or x.startswith("/") or ".." in x.split("/")
                for x in tests):
            raise ValueError("invalid_test_reference")
        for w in window:
            if w["last"] < first:
                continue
            # Before the verified repair boundary, this defect was unresolved.
            repaired = row["state"] in CLOSED and w["last"] >= resolution
            key = ("historical_repair_record_ids" if repaired
                   else "open_carry_forward_ids")
            w[key].append(fid)
    for w in window:
        w["historical_repair_record_ids"].sort()
        w["open_carry_forward_ids"].sort()
    return {
        "schema": "tcg-version-carry-forward-summary/v1",
        "baseline_main_sha": base, "tested_candidate_head": head,
        "scope": "selected_finding_records_not_complete_version_review",
        "finding_count": len(ids),
        "window_carry_forward": window,
        "complete_version_reviews": 0, "quality_score": None,
        "device": "DEVICE_UNVERIFIED", "release_approval": False,
    }


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument("--ledger",type=Path,default=Path(__file__).resolve().parent/
                        "evidence/version_review_findings_v001_v879.json")
    parser.add_argument("--latest",type=int,default=879)
    args=parser.parse_args()
    try:
        root=args.root.resolve()
        head=git(root,"rev-parse","--verify","HEAD^{commit}").decode("ascii").strip()
        result=validate(read_json(args.ledger),root,head=head,latest=args.latest)
    except (ValueError,OSError,UnicodeError,subprocess.SubprocessError) as exc:
        print(json.dumps({"status":"HOLD","reason":str(exc)[:180]}))
        return 2
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())

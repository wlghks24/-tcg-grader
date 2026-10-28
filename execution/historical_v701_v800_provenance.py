#!/usr/bin/env python3
"""W701–W800 strict provenance-lead scan, never a software release certificate.

Searches protected main's COMPLETE reachable commit messages (not just titles)
and available local tag/remote-ref names for standalone V701..V800 tokens.
Does not run TCG scripts, mutate files, fetch HTTP, or infer missing releases.
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

PROTECTED_MAIN = "6c78831bbb6e188717f86ef90243a836d2e0b67a"
TOKEN = re.compile(r"(?<![A-Za-z0-9])v0*(7[0-9]{2}|800)(?![A-Za-z0-9])", re.I)
COMMIT = re.compile(r"^[0-9a-f]{40}$")
MAX_COMMITS = 20_000
MAX_REFS = 20_000


def git(root: Path, *args: str, timeout: int = 90) -> bytes:
    p = subprocess.run(["git", *args], cwd=root, capture_output=True,
                       check=False, timeout=timeout)
    if p.returncode:
        raise ValueError("git_provenance_unavailable:" + (args[0] if args else "unknown"))
    return p.stdout


def tokens(text: str) -> list[int]:
    return sorted({int(x) for x in TOKEN.findall(text)
                   if 701 <= int(x) <= 800})


def scan(root: Path, base: str = PROTECTED_MAIN) -> dict[str, Any]:
    root = root.resolve()
    if not COMMIT.fullmatch(base):
        raise ValueError("invalid_historical_base")
    exact = git(root, "rev-parse", "--verify", base + "^{commit}").decode("ascii").strip()
    if exact != base:
        raise ValueError("historical_base_drift")
    head = git(root, "rev-parse", "--verify", "HEAD^{commit}").decode("ascii").strip()
    if not COMMIT.fullmatch(head):
        raise ValueError("bad_worktree_head")
    git(root, "merge-base", "--is-ancestor", base, head)
    n = int(git(root, "rev-list", "--count", base).decode("ascii").strip())
    if not 0 < n <= MAX_COMMITS:
        raise ValueError("commit_scan_budget_or_empty_history")
    raw = git(root, "log", "-z", "--format=%H%x09%B", base, timeout=120)
    messages = [x for x in raw.split(b"\0") if x.strip()]
    if len(messages) != n:
        raise ValueError("incomplete_commit_body_scan")
    commit_hints: list[dict[str, Any]] = []
    for item in messages:
        commit, sep, message = item.partition(b"\t")
        if sep != b"\t" or COMMIT.fullmatch(commit.decode("ascii", "strict")) is None:
            raise ValueError("invalid_commit_message_frame")
        txt = message.decode("utf-8", "strict")
        found = tokens(txt)
        if found:
            commit_hints.append({"commit": commit.decode("ascii"),
                                 "version_tokens": found,
                                 "classification": "COMMIT_BODY_TOKEN_NOT_RELEASE_PROOF"})
    ref_raw = git(root, "for-each-ref", "--format=%(refname)",
                  "refs/tags", "refs/remotes/origin")
    names = [x for x in ref_raw.decode("utf-8", "strict").splitlines() if x]
    if len(names) > MAX_REFS or len(names) != len(set(names)):
        raise ValueError("unbounded_or_duplicate_refs")
    ref_hints = [{"ref": name, "version_tokens": tokens(name),
                  "classification": "REF_NAME_TOKEN_NOT_RELEASE_PROOF"}
                 for name in names if tokens(name)]
    return {
        "schema": "tcg-w701-provenance-scan/v1",
        "protected_main_sha": base,
        "candidate_head_sha": head,
        "reachable_baseline_commits_examined": n,
        "local_refs_examined": len(names),
        "commit_body_token_hints": commit_hints,
        "tag_and_remote_ref_token_hints": ref_hints,
        "commit_body_token_hits": len(commit_hints),
        "ref_name_token_hits": len(ref_hints),
        "absence_of_tokens_proves_no_release": False,
        "every_version_reviewed": False,
        "quality_score": None,
        "tablet_device_verified": False,
        "status": "PROVENANCE_LEADS_ONLY_REVIEW_REQUIRED"
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = ap.parse_args()
    try:
        data = scan(args.root)
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc)[:160]}))
        return 2
    print(json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

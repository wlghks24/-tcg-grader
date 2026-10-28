#!/usr/bin/env python3
"""Fail-closed read-only preflight for two immutable TCG sync watch contracts.

This does NOT validate or create a successor; it identifies changes that require
a separately reviewed successor generation before merging. No source writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

CONTRACTS = (
    "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V426.json",
    "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V646.json",
)
SHA_RE = re.compile(r"[0-9a-f]{40}")


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True,
                            check=False, timeout=40)
    if result.returncode:
        raise ValueError("git_preflight_failed:" + (args[0] if args else "unknown"))
    return result.stdout


def sha_ref(root: Path, candidate: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9._/\-]{1,150}", candidate):
        raise ValueError("invalid_ref")
    resolved = git(root, "rev-parse", "--verify", candidate + "^{commit}").decode("ascii").strip()
    if SHA_RE.fullmatch(resolved) is None:
        raise ValueError("invalid_commit_sha")
    return resolved


def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("duplicate_contract_key")
        data[key] = value
    return data


def contract_watch(root: Path, base: str, path: str) -> dict[str, Any]:
    raw = git(root, "show", f"{base}:{path}")
    if len(raw) > 250_000:
        raise ValueError("oversized_contract")
    data = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique,
                      parse_constant=lambda _n: (_ for _ in ()).throw(
                          ValueError("non_finite_contract")))
    if not isinstance(data, dict):
        raise ValueError("malformed_contract")
    watcher = data.get("freshness_watch")
    if not isinstance(watcher, dict):
        raise ValueError("missing_freshness_watch")
    fields = {}
    for key in ("exact_paths", "path_prefixes", "exclude_paths"):
        value = watcher.get(key, [])
        if not isinstance(value, list) or any(not isinstance(x, str) or not x for x in value):
            raise ValueError("malformed_watch_paths:" + key)
        fields[key] = frozenset(value) if key != "path_prefixes" else tuple(value)
    fields["contract"] = path
    fields["sha256"] = hashlib.sha256(raw).hexdigest()
    return fields


def classify(paths: list[str], watchers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for path in sorted(set(paths)):
        reasons = []
        if path in CONTRACTS:
            reasons.append({"contract": path, "rule": "protected_contract_modified"})
        for watch in watchers:
            if path in watch["exclude_paths"]:
                continue
            if path in watch["exact_paths"]:
                reasons.append({"contract": watch["contract"], "rule": "exact_path"})
            elif any(path.startswith(prefix) for prefix in watch["path_prefixes"]):
                reasons.append({"contract": watch["contract"], "rule": "path_prefix"})
        if reasons:
            matched.append({"path": path, "matched_watch": reasons})
    return matched


def inspect(root: Path, base_ref: str, head_ref: str) -> dict[str, Any]:
    root = root.resolve()
    base = sha_ref(root, base_ref)
    head = sha_ref(root, head_ref)
    git(root, "merge-base", "--is-ancestor", base, head)
    raw = git(root, "diff", "--no-renames", "--name-only", "-z", base, head, "--")
    paths = [b.decode("utf-8", "strict") for b in raw.split(b"\0") if b]
    if len(paths) > 10_000:
        raise ValueError("changed_path_budget_exceeded")
    watch = [contract_watch(root, base, name) for name in CONTRACTS]
    results = classify(paths, watch)
    return {
        "schema": "tcg-sync-watched-path-preflight/v1",
        "base": base,
        "head": head,
        "changed_path_count": len(paths),
        "checked_contracts": [{"path": w["contract"], "sha256": w["sha256"]} for w in watch],
        "requires_successor_review": bool(results),
        "watched_changes": results,
        "status": "HOLD_REVIEW_SUCCESSOR" if results else "NO_WATCHED_DIFF_IN_TWO_CONTRACTS",
        "device": "DEVICE_UNVERIFIED",
        "not_a_successor_approval": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", default="HEAD")
    a = parser.parse_args()
    try:
        payload = inspect(a.root, a.base, a.head)
    except (OSError, ValueError, UnicodeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "HOLD_ERROR", "reason": str(exc)[:160],
                          "not_a_successor_approval": True}))
        return 2
    print(json.dumps(payload, sort_keys=True, indent=2))
    return 3 if payload["requires_successor_review"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

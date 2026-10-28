#!/usr/bin/env python3
"""Read-only, evidence-only V100-window inventory for TCG Grader.

File/commit V tokens are *leads*, never proof of a release or a fixed defect.
No imports from the running TCG application, network calls, device access or writes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

SCHEMA = "tcg-version-window-inventory/v1"
VERSION_RE = re.compile(r"(?<![A-Za-z0-9])v0*([1-9][0-9]{0,3})(?![A-Za-z0-9])", re.I)
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
CROSS_PROJECT = (
    "instagram_tcg_content/",
    "TCG_CROSSCHECK/IG_CARDINFO/",
    "ai_reliability_v8/",
    "tcg_reliability/ai_reliability_v8/",
)


def versions(text: str, first: int, last: int) -> list[int]:
    """Return only bounded, standalone V-number tokens, not dates or PR numbers."""
    return sorted({int(match) for match in VERSION_RE.findall(text)
                   if first <= int(match) <= last})


def canonical_sha256(payload: dict[str, Any]) -> str:
    stable = {key: value for key, value in payload.items() if key != "checkpoint_sha256"}
    encoded = json.dumps(stable, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def git(root: Path, *args: str, timeout: int = 75) -> bytes:
    proc = subprocess.run(
        ["git", *args], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=timeout,
    )
    if proc.returncode:
        raise ValueError("git_inventory_unavailable")
    return proc.stdout


def read_previous(path: Path, *, first: int, head: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1_000_000:
        raise ValueError("unsafe_previous_checkpoint")
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate_previous_key")
            result[key] = value
        return result
    prior = json.loads(path.read_text("utf-8"), object_pairs_hook=unique,
                       parse_constant=lambda _v: (_ for _ in ()).throw(
                           ValueError("non_finite_previous")))
    if not isinstance(prior, dict) or prior.get("schema") != SCHEMA:
        raise ValueError("wrong_previous_schema")
    digest = prior.get("checkpoint_sha256")
    if not isinstance(digest, str) or not SHA_RE.fullmatch(digest):
        raise ValueError("invalid_previous_digest")
    if digest != canonical_sha256(prior):
        raise ValueError("tampered_previous_checkpoint")
    if not isinstance(prior.get("window"), dict) or prior["window"].get("end") != first - 1:
        raise ValueError("non_contiguous_windows")
    if not isinstance(prior.get("source"), dict) or prior["source"].get("head") != head:
        raise ValueError("source_head_changed_revalidate_prior_window")
    return prior


def inventory(root: Path, first: int, previous: dict[str, Any] | None = None,
              max_commits: int = 12_000) -> dict[str, Any]:
    if first < 1 or (first - 1) % 100 or first > 9901:
        raise ValueError("window_start_must_be_1_101_201")
    if not 1 <= max_commits <= 20_000:
        raise ValueError("invalid_commit_budget")
    root = root.resolve()
    head = git(root, "rev-parse", "--verify", "HEAD^{commit}").decode("ascii").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise ValueError("invalid_git_head")
    if previous is not None:
        if previous.get("checkpoint_sha256") != canonical_sha256(previous):
            raise ValueError("tampered_previous_checkpoint")
        if not isinstance(previous.get("window"), dict) or previous["window"].get("end") != first - 1:
            raise ValueError("non_contiguous_windows")
        if not isinstance(previous.get("source"), dict) or previous["source"].get("head") != head:
            raise ValueError("source_head_changed_revalidate_prior_window")
    last = first + 99
    tracked: list[dict[str, Any]] = []
    excluded = 0
    unsafe = 0
    tree = git(root, "ls-tree", "-r", "-z", head)
    for item in tree.split(b"\0"):
        if not item:
            continue
        meta, raw_path = item.split(b"\t", 1)
        mode, kind, blob = meta.decode("ascii").split()
        path = raw_path.decode("utf-8", "strict")
        tokens = versions(path, first, last)
        if not tokens:
            continue
        if path.startswith(CROSS_PROJECT):
            excluded += 1
            continue
        if mode == "120000" or kind != "blob":
            unsafe += 1
            continue
        tracked.append({"path": path, "tokens": tokens, "git_blob": blob,
                        "classification": "filename_hint_only"})
    tracked.sort(key=lambda item: item["path"])
    log = git(root, "log", f"--max-count={max_commits}",
              "--format=%H%x09%s", head, timeout=90).decode("utf-8", "strict")
    subjects: list[dict[str, Any]] = []
    history_lines = log.splitlines()
    for line in history_lines:
        commit, sep, subject = line.partition("\t")
        if not sep or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("unexpected_git_log_format")
        tokens = versions(subject, first, last)
        if tokens:
            subjects.append({"commit": commit, "tokens": tokens,
                             "subject": subject[:220],
                             "classification": "commit_subject_hint_only"})
    shallow = git(root, "rev-parse", "--is-shallow-repository").strip() == b"true"
    candidate_tokens = sorted({v for row in tracked + subjects for v in row["tokens"]})
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "window": {"start": first, "end": last},
        "source": {"head": head, "is_shallow": shallow,
                   "history_limited": len(history_lines) >= max_commits},
        "previous_checkpoint_sha256": previous.get("checkpoint_sha256") if previous else None,
        "candidate_version_tokens": candidate_tokens,
        "path_hints": tracked,
        "commit_subject_hints": subjects,
        "excluded_cross_project_paths": excluded,
        "unsafe_versioned_paths": unsafe,
        "carry_forward": previous.get("carry_forward", []) if previous else [],
        "status": "INVENTORY_ONLY_NOT_RELEASE_VERIFIED",
        "tests": "NOT_RUN",
        "device": "DEVICE_UNVERIFIED",
        "score": None,
    }
    payload["checkpoint_sha256"] = canonical_sha256(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--previous", type=Path)
    parser.add_argument("--max-commits", type=int, default=12_000)
    options = parser.parse_args()
    try:
        root = options.root.resolve()
        head = git(root, "rev-parse", "--verify", "HEAD^{commit}").decode("ascii").strip()
        previous = read_previous(options.previous, first=options.start, head=head) if options.previous else None
        result = inventory(root, options.start, previous, options.max_commits)
    except (OSError, UnicodeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "HOLD", "reason": str(exc)[:160]}))
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

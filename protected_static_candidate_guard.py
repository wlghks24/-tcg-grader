#!/usr/bin/env python3
"""Fail closed for protected static-data candidate branches.

A branch named auto/static-data-* is a data-only promotion surface. It may
contain only the approved public JSON outputs, integrity_manifest.json, and at
most one complete Tablet GPT sync metadata generation. Security is enforced by
exact paths and generation completeness rather than commit-message wording.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from tablet_collection_publish import OUTPUTS

BRANCH_RE = re.compile(r"^auto/static-data-[A-Za-z0-9._-]{1,120}$")
ALLOWED_FILES = frozenset(OUTPUTS) | {"integrity_manifest.json"}
MAX_REPORT_AGE = dt.timedelta(hours=2)
MAX_FUTURE_SKEW = dt.timedelta(minutes=5)
DATA_COMMIT_PREFIX = "data: refresh validated TCG static snapshot"
SYNC_PATTERNS = (
    re.compile(r"^TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V(\d+)\.json$"),
    re.compile(r"^TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v(\d+)_delta\.json$"),
    re.compile(r"^TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v(\d+)\.json$"),
    re.compile(r"^test_tablet_gpt_tcg_grader_sync_v(\d+)\.py$"),
)


def sync_generation_version(path: str) -> int | None:
    for pattern in SYNC_PATTERNS:
        match = pattern.fullmatch(path)
        if match:
            return int(match.group(1))
    return None


def expected_sync_generation_files(version: int) -> set[str]:
    return {
        f"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V{version}.json",
        f"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v{version}_delta.json",
        f"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v{version}.json",
        f"test_tablet_gpt_tcg_grader_sync_v{version}.py",
    }


class StaticCandidateGuardError(ValueError):
    pass


def fail(code: str, detail: str) -> None:
    raise StaticCandidateGuardError(f"{code}: {detail}")


def parse_report_finished_at(report: dict) -> dt.datetime:
    value = report.get("finished_at")
    if not isinstance(value, str) or not value:
        fail("STATIC_CANDIDATE_REPORT_MISSING_TIME", "auto_update_report.finished_at is required")
    try:
        stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail("STATIC_CANDIDATE_REPORT_BAD_TIME", f"invalid finished_at={value!r}")
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        fail("STATIC_CANDIDATE_REPORT_BAD_TIME", "finished_at must be timezone-aware")
    return stamp.astimezone(dt.timezone.utc)


def validate_candidate(branch: str, commits: list[dict], report: dict,
                       *, now: dt.datetime | None = None) -> str:
    if not branch.startswith("auto/static-data-"):
        return "STATIC_CANDIDATE_GUARD_NOT_APPLICABLE"
    if not BRANCH_RE.fullmatch(branch):
        fail("STATIC_CANDIDATE_BAD_BRANCH", f"invalid branch name={branch!r}")
    if not commits:
        fail("STATIC_CANDIDATE_EMPTY", "candidate branch has no commits beyond its base")

    changed: set[str] = set()
    sync_files_by_version: dict[int, set[str]] = {}
    for index, row in enumerate(commits):
        parents = row.get("parents")
        paths = set(row.get("paths") or ())
        subject = row.get("subject", "")
        if parents != 1:
            fail("STATIC_CANDIDATE_NONLINEAR_HISTORY", f"commit={row.get('sha')} parents={parents}")

        sync_paths = {path for path in paths if sync_generation_version(path) is not None}
        forbidden = sorted(paths - ALLOWED_FILES - sync_paths)
        if forbidden:
            fail(
                "STATIC_CANDIDATE_SCOPE_VIOLATION",
                f"commit={row.get('sha')} forbidden={','.join(forbidden)}",
            )
        if index == 0:
            if not str(subject).startswith(DATA_COMMIT_PREFIX):
                fail(
                    "STATIC_CANDIDATE_BAD_ORIGIN",
                    f"first commit must start with {DATA_COMMIT_PREFIX!r}",
                )
            if sync_paths:
                fail("STATIC_CANDIDATE_SYNC_IN_ORIGIN", "sync metadata must follow the data commit")
        elif sync_paths:
            # Commit messages are descriptive metadata, not a security boundary. Keep
            # sync follow-ups path-pure instead: only the exact versioned sync files
            # and an optional integrity manifest may share the commit.
            mixed = sorted(paths - sync_paths - {"integrity_manifest.json"})
            if mixed:
                fail(
                    "STATIC_CANDIDATE_MIXED_SYNC_COMMIT",
                    f"commit={row.get('sha')} mixed={','.join(mixed)}",
                )

        for path in sync_paths:
            version = sync_generation_version(path)
            assert version is not None
            sync_files_by_version.setdefault(version, set()).add(path)
        changed.update(paths)

    if len(sync_files_by_version) > 1:
        fail(
            "STATIC_CANDIDATE_MULTIPLE_SYNC_GENERATIONS",
            f"versions={','.join(map(str, sorted(sync_files_by_version)))}",
        )
    for version, paths in sync_files_by_version.items():
        expected = expected_sync_generation_files(version)
        if paths != expected:
            missing = sorted(expected - paths)
            extra = sorted(paths - expected)
            fail(
                "STATIC_CANDIDATE_INCOMPLETE_SYNC_GENERATION",
                f"version={version} missing={','.join(missing)} extra={','.join(extra)}",
            )

    if not (changed & set(OUTPUTS)):
        fail("STATIC_CANDIDATE_NO_PUBLIC_DATA", "candidate changes no approved public JSON")
    if "auto_update_report.json" not in changed:
        fail(
            "STATIC_CANDIDATE_REPORT_NOT_BOUND",
            "auto_update_report.json must be part of the candidate diff",
        )

    stamp = parse_report_finished_at(report)
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        fail("STATIC_CANDIDATE_BAD_CLOCK", "validation clock must be timezone-aware")
    age = now.astimezone(dt.timezone.utc) - stamp
    if age < -MAX_FUTURE_SKEW:
        fail("STATIC_CANDIDATE_REPORT_FROM_FUTURE", f"age_seconds={age.total_seconds():.0f}")
    if age > MAX_REPORT_AGE:
        fail(
            "STATIC_CANDIDATE_REPORT_STALE",
            f"age_hours={age.total_seconds()/3600:.2f} max_hours=2",
        )
    return "STATIC_CANDIDATE_SCOPE_AND_FRESHNESS_OK"


def git(root: Path, *args: str) -> str:
    cp = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return cp.stdout.strip()


def current_branch() -> str:
    return (
        os.environ.get("GITHUB_HEAD_REF")
        or os.environ.get("GITHUB_REF_NAME")
        or ""
    ).strip()


def prepare_candidate_ref(root: Path, branch: str) -> str:
    shallow = git(root, "rev-parse", "--is-shallow-repository").lower() == "true"
    if shallow:
        git(root, "fetch", "--unshallow", "--no-tags", "origin")
    remote_ref = f"refs/remotes/origin/{branch}"
    git(
        root,
        "fetch",
        "--no-tags",
        "origin",
        "+refs/heads/main:refs/remotes/origin/main",
        f"+refs/heads/{branch}:{remote_ref}",
    )
    return remote_ref


def resolve_base(root: Path, target_ref: str) -> str:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path:
        try:
            payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
            sha = payload.get("pull_request", {}).get("base", {}).get("sha")
            if isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha):
                git(root, "cat-file", "-e", f"{sha}^{{commit}}")
                return sha
        except (OSError, ValueError, TypeError, subprocess.CalledProcessError):
            pass
    return git(root, "merge-base", target_ref, "refs/remotes/origin/main")


def collect_commits(root: Path, base: str, target_ref: str) -> list[dict]:
    lines = git(root, "rev-list", "--reverse", "--parents", f"{base}..{target_ref}").splitlines()
    rows = []
    for line in lines:
        parts = line.split()
        if not parts:
            continue
        sha, parents = parts[0], parts[1:]
        touched = git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", sha).splitlines()
        subject = git(root, "show", "-s", "--format=%s", sha)
        rows.append({
            "sha": sha,
            "parents": len(parents),
            "paths": [path for path in touched if path],
            "subject": subject,
        })
    return rows


def main() -> int:
    branch = current_branch()
    if not branch.startswith("auto/static-data-"):
        print("STATIC_CANDIDATE_GUARD_NOT_APPLICABLE")
        return 0
    root = Path(__file__).resolve().parent
    try:
        if not BRANCH_RE.fullmatch(branch):
            fail("STATIC_CANDIDATE_BAD_BRANCH", f"invalid branch name={branch!r}")
        target_ref = prepare_candidate_ref(root, branch)
        base = resolve_base(root, target_ref)
        commits = collect_commits(root, base, target_ref)
        report = json.loads(git(root, "show", f"{target_ref}:auto_update_report.json"))
        result = validate_candidate(branch, commits, report)
        print(f"{result} branch={branch} base={base} commits={len(commits)}")
        return 0
    except (OSError, KeyError, TypeError, json.JSONDecodeError,
            subprocess.CalledProcessError, StaticCandidateGuardError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

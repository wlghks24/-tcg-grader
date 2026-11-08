#!/usr/bin/env python3
"""V976 explicit tablet release handoff. Default: READ ONLY; no network/install."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
from execution import tablet_release_preflight_v972 as old
from execution import apply_tablet_candidate_v897 as handoff

V927 = "cd7b40afcd9bdfadb0987a70847eee1c3a9f08f8"
V975 = "9e93fdc2d3ba9a06b310a06bdf1bc8f0e454b1e0"
SELF = "execution/tablet_release_install_v976.py"
TEST = "test_tablet_release_install_v976.py"
V976_DIFF = {SELF: "A", TEST: "A", "integrity_manifest.json": "M"}
OLD_REPORT = "v31_최종검증보고서.json"
ARCHIVED_REPORT = "docs/archive/reports/" + OLD_REPORT
FULL_SHA = re.compile(r"[0-9a-f]{40}\Z")


class ReleaseHold(ValueError):
    """Never stop or switch when this is raised."""


def git(repo, *args, allow_one=False):
    return old._git(repo, *args, allow_one=allow_one)[1]


def exact_ancestor(repo, older, newer):
    rc, _ = old._git(repo, "merge-base", "--is-ancestor", older, newer, allow_one=True)
    return rc == 0


def target_file(repo, sha, path):
    return git(repo, "show", sha + ":" + path)


def paths(repo, *args):
    return old._paths(git(repo, *args))


def inspect(repo, base, target, *, source_file=None):
    """Exact offline ancestry, worktree, local data, Git mode and collision gate."""
    if not all(isinstance(s, str) and FULL_SHA.fullmatch(s) for s in (base, target)):
        raise ReleaseHold("FULL_COMMIT_SHA_REQUIRED")
    repo = Path(repo)
    source_file = Path(__file__) if source_file is None else Path(source_file)
    if repo.is_symlink() or not repo.is_dir() or not (repo / ".git").is_dir():
        raise ReleaseHold("REGULAR_LIVE_CHECKOUT_REQUIRED")
    repo = repo.resolve(strict=True)
    if source_file.is_symlink() or not source_file.is_file():
        raise ReleaseHold("REVIEWED_INSTALLER_FILE_REQUIRED")
    source_file = source_file.resolve(strict=True)
    stage = source_file.parents[1]
    if source_file.relative_to(stage).as_posix() != SELF or stage == repo:
        raise ReleaseHold("SEPARATE_REVIEW_WORKTREE_REQUIRED")
    if Path(old._text(git(repo, "rev-parse", "--show-toplevel"))).resolve() != repo:
        raise ReleaseHold("LIVE_REPO_ROOT_MISMATCH")
    if Path(old._text(git(stage, "rev-parse", "--show-toplevel"))).resolve() != stage:
        raise ReleaseHold("REVIEW_STAGE_ROOT_MISMATCH")
    if old._text(git(repo, "rev-parse", "HEAD")) != base:
        raise ReleaseHold("LIVE_HEAD_CHANGED")
    if old._text(git(stage, "rev-parse", "HEAD")) != target:
        raise ReleaseHold("STAGED_HEAD_NOT_TARGET")
    if not exact_ancestor(repo, V927, base) or not exact_ancestor(repo, base, V975):
        raise ReleaseHold("UNREVIEWED_LIVE_BASE")
    parents = old._text(git(repo, "rev-list", "--parents", "-n", "1", target)).split()
    if parents != [target, V975]:
        raise ReleaseHold("TARGET_NOT_EXACT_V975_CHILD")
    changed = {p: s for s, p in old._changes(
        git(repo, "diff", "--no-renames", "--name-status", "-z", V975, target))}
    if changed != V976_DIFF:
        raise ReleaseHold("UNREVIEWED_V976_TARGET_DELTA")
    if source_file.read_bytes() != target_file(repo, target, SELF):
        raise ReleaseHold("STAGED_INSTALLER_BYTES_CHANGED")
    manifest = json.loads(target_file(repo, target, "integrity_manifest.json"))
    for path in (SELF, TEST):
        raw = target_file(repo, target, path)
        record = manifest.get("files", {}).get(path)
        if record != {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}:
            raise ReleaseHold("TARGET_MANIFEST_MISMATCH:" + path)
    if not exact_ancestor(repo, base, target):
        raise ReleaseHold("TARGET_NOT_DESCENDANT")
    changes = old._changes(
        git(repo, "diff", "--no-renames", "--name-status", "-z", base, target))
    candidate_paths = {p for _, p in changes}
    if not changes or len(changes) > 100:
        raise ReleaseHold("RELEASE_DIFF_SIZE_UNREVIEWED")
    for status, path in changes:
        if status == "D":
            if path != OLD_REPORT:
                raise ReleaseHold("UNREVIEWED_FILE_DELETION:" + path)
            if target_file(repo, base, path) != target_file(repo, target, ARCHIVED_REPORT):
                raise ReleaseHold("HISTORICAL_REPORT_NOT_PRESERVED")
            continue
        if status not in ("A", "M") or old._mode(repo, target, path) not in ("100644", "100755"):
            raise ReleaseHold("UNSAFE_TARGET_OBJECT:" + path)
        if "/" not in path and path.endswith(".json") and path != "integrity_manifest.json":
            raise ReleaseHold("MUTABLE_ROOT_JSON_TARGET_CHANGE:" + path)
        for parent in (repo / path).parents:
            if parent == repo.parent:
                break
            if parent.is_symlink():
                raise ReleaseHold("LIVE_PATH_PARENT_SYMLINK:" + path)
    staged = set(paths(repo, "diff", "--cached", "--name-only", "-z"))
    dirty = set(paths(repo, "diff", "--name-only", "-z"))
    if staged:
        raise ReleaseHold("STAGED_DEVICE_EDITS")
    if dirty & candidate_paths:
        raise ReleaseHold("OVERLAPPING_LOCAL_EDITS")
    if any("/" in p or not p.endswith(".json") or p == "integrity_manifest.json" for p in dirty):
        raise ReleaseHold("UNEXPECTED_LOCAL_SOURCE_DIRTY")
    literal = [":(literal)" + p for p in sorted(candidate_paths)]
    for args, reason in (
        (("ls-files", "--others", "-z", "--", *literal), "UNTRACKED_COLLISION"),
        (("ls-files", "--others", "--ignored", "--exclude-standard", "-z", "--", *literal),
         "IGNORED_COLLISION"),
    ):
        if paths(repo, *args):
            raise ReleaseHold(reason)
    root_json = list(repo.glob("*.json"))
    if any(p.is_symlink() or not p.is_file() for p in root_json):
        raise ReleaseHold("ROOT_JSON_NOT_REGULAR")
    data_bytes = sum(p.stat().st_size for p in root_json)
    if data_bytes > 500_000_000:
        raise ReleaseHold("BACKUP_TOO_LARGE")
    if shutil.disk_usage(repo.parent).free < max(2 * data_bytes + 100_000_000, 300_000_000):
        raise ReleaseHold("INSUFFICIENT_BACKUP_SPACE")
    return {"status": "READY_FOR_EXPLICIT_DEVICE_APPLY", "expected_base": base,
            "target": target, "changed_paths": len(changes),
            "historical_report_preserved": True, "root_json_bytes_to_backup": data_bytes,
            "local_mutable_root_json_count": len([p for p in dirty if p.endswith(".json")]),
            "installer_source_verified": True, "installation_completed": False,
            "physical_tablet_verified": False, "photos_touched": False}


def verify_backup(repo, folder):
    """Compare private backup tar member hashes to stopped live JSON; no extraction."""
    if (folder / "BASE_SHA.txt").is_symlink():
        raise ReleaseHold("BACKUP_SHA_SYMLINK")
    expected = {p.name: p for p in repo.glob("*.json")}
    seen = set()
    with tarfile.open(folder / "runtime-json.tar.gz", "r:gz") as archive:
        for member in archive:
            if not member.isfile() or member.name not in expected or member.name in seen:
                raise ReleaseHold("BACKUP_UNSAFE_MEMBER")
            seen.add(member.name)
            stream = archive.extractfile(member)
            if stream is None:
                raise ReleaseHold("BACKUP_UNREADABLE")
            digest = hashlib.sha256()
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
            with expected[member.name].open("rb") as current_file:
                current = hashlib.file_digest(current_file, "sha256").hexdigest()
            if digest.hexdigest() != current or member.size != expected[member.name].stat().st_size:
                raise ReleaseHold("BACKUP_MISMATCH")
    if seen != set(expected):
        raise ReleaseHold("BACKUP_INCOMPLETE")


def apply(repo, base, target, *, source_file=None):
    """User-authorized stop/backup/switch/launch using exact V974 reviewed helper."""
    inspect(repo, base, target, source_file=source_file)
    repo = Path(repo).resolve(strict=True)
    saved = None
    stopped = False
    try:
        handoff.require_startup_readiness(repo)
        handoff.stop_launcher(repo)
        stopped = True
        inspect(repo, base, target, source_file=source_file)
        saved = handoff.backup(handoff.Plan(repo, base, target))
        verify_backup(repo, saved)
        inspect(repo, base, target, source_file=source_file)
        if handoff.port_open():
            raise ReleaseHold("SERVER_RESTARTED_BEFORE_SWITCH")
        handoff.switch_and_check(handoff.Plan(repo, base, target))
        print(json.dumps({
            "status": "SOURCE_SWITCHED_START_PENDING", "backup": str(saved), "target": target,
            "next": "Run python -m execution.tablet_device_readback_v897 --expected-sha " + target
        }, ensure_ascii=False), flush=True)
        os.chdir(repo)
        os.execvp("bash", ["bash", handoff.LAUNCH])
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as exc:
        print(json.dumps({
            "status": "HOLD_DEVICE_APPLY_INCOMPLETE", "server_stop_completed": stopped,
            "backup": str(saved) if saved else None,
            "reason": str(exc)[:180] if isinstance(exc, ValueError) else type(exc).__name__,
            "next": "Inspect HEAD and launcher state; never reset, force or delete learning files."
        }, ensure_ascii=False), flush=True)
        return 2


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--expected-base", required=True)
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-target", default="")
    args = parser.parse_args(argv)
    try:
        report = inspect(args.repo, args.expected_base, args.target_sha)
        if not args.apply:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        if args.confirm_target != args.target_sha:
            raise ReleaseHold("EXPLICIT_FULL_SHA_CONFIRMATION_REQUIRED")
        return apply(args.repo, args.expected_base, args.target_sha)
    except (ReleaseHold, old.PreflightHold, OSError, ValueError, subprocess.SubprocessError,
            UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "HOLD_PREFLIGHT_NO_DEVICE_ACTION",
                          "reason": str(exc)[:180] if isinstance(exc, ValueError) else type(exc).__name__,
                          "installation_completed": False}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""V977 read-only backup coverage audit; never archives, stops or mutates files."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path

DATA_HINTS = ("photo", "image", "model", "learn", "train", "label", "review", "archive", "dataset")
SKIP_DIRS = frozenset((".git", ".venv", "venv", "__pycache__", "node_modules"))


def audit(repo: Path, *, max_files: int = 100000):
    repo = Path(repo).expanduser()
    if repo.is_symlink() or not repo.is_dir() or not (repo / ".git").is_dir():
        raise ValueError("REGULAR_LIVE_REPO_REQUIRED")
    repo = repo.resolve(strict=True)
    reasons = []
    groups = {"root_json": 0, "nested_data": 0}
    bytes_by_group = {"root_json": 0, "nested_data": 0}
    fingerprints = hashlib.sha256()
    count = 0
    stack = [repo]
    while stack:
        folder = stack.pop()
        try:
            children = sorted(folder.iterdir(), key=lambda p: p.name)
        except OSError:
            reasons.append("DIRECTORY_UNREADABLE")
            continue
        for path in children:
            relative = path.relative_to(repo).as_posix()
            if path.is_symlink():
                reasons.append("SYMLINK_REQUIRES_REVIEW")
                continue
            try:
                if path.is_dir():
                    if path.name not in SKIP_DIRS:
                        stack.append(path)
                    continue
                if not path.is_file():
                    reasons.append("SPECIAL_FILE_REQUIRES_REVIEW")
                    continue
                group = ("root_json" if path.parent == repo and path.suffix.lower() == ".json"
                         else "nested_data" if path.parent != repo and any(
                             hint in relative.lower() for hint in DATA_HINTS) else None)
                if group is None:
                    continue
                count += 1
                if count > max_files:
                    reasons.append("INVENTORY_LIMIT_EXCEEDED")
                    stack.clear()
                    break
                before = path.stat()
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
                after = path.stat()
                if (before.st_size, before.st_mtime_ns, before.st_ino) != (
                        after.st_size, after.st_mtime_ns, after.st_ino):
                    reasons.append("FILE_CHANGED_DURING_SCAN")
                groups[group] += 1
                bytes_by_group[group] += after.st_size
                fingerprints.update((group + "\0" + relative + "\0" + str(after.st_size)
                                     + "\0" + digest.hexdigest() + "\n").encode())
            except OSError:
                reasons.append("FILE_UNREADABLE_OR_DISAPPEARED")
    if groups["nested_data"]:
        reasons.append("NESTED_DATA_NOT_COVERED_BY_V976_ROOT_JSON_BACKUP")
    reasons.append("NO_COMPLETE_VERIFIED_BACKUP_OR_RESTORE_PROOF")
    return {"status": "HOLD_NO_DEVICE_ACTION", "counts": groups,
            "bytes": bytes_by_group, "inventory_sha256": fingerprints.hexdigest(),
            "reasons": sorted(set(reasons)), "installation_completed": False,
            "files_written": False, "signals_sent": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit(args.repo)
    except (OSError, ValueError) as exc:
        result = {"status": "HOLD_NO_DEVICE_ACTION", "reasons": [str(exc)],
                  "files_written": False, "signals_sent": False}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""V1013 read-only comparison. Matching bytes never prove physical off-device storage."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

class Hold(Exception):
    pass

def inventory(root: Path) -> dict[str, tuple[str, int]]:
    if root.is_symlink() or not root.is_dir():
        raise Hold('unsafe_root')
    found = {}
    for directory, dirs, files in os.walk(root, topdown=True, followlinks=False):
        for name in dirs:
            p = Path(directory) / name
            if p.is_symlink() or not p.is_dir():
                raise Hold('unsafe_directory')
        for name in files:
            p = Path(directory) / name
            if p.is_symlink():
                raise Hold('unsafe_file')
            rel = p.relative_to(root).as_posix()
            if rel in found:
                raise Hold('duplicate_file')
            flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
            try:
                fd = os.open(p, flags)
                with os.fdopen(fd, 'rb') as handle:
                    before = os.fstat(handle.fileno())
                    if not stat.S_ISREG(before.st_mode):
                        raise Hold('nonregular_file')
                    h = hashlib.sha256()
                    count = 0
                    for block in iter(lambda: handle.read(1024 * 1024), b''):
                        count += len(block)
                        h.update(block)
                    after = os.fstat(handle.fileno())
                    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns) or count != before.st_size:
                        raise Hold('changed_during_read')
                    found[rel] = (h.hexdigest(), count)
            except OSError as exc:
                raise Hold('file_unreadable') from exc
    return found

def compare(a: Path, b: Path) -> dict:
    report = {'schema': 'tcg-offdevice-compare-v1013', 'comparison_pass': False,
              'offdevice_copy_verified': False, 'physical_tablet_verified': False,
              'ready_for_migration': False}
    try:
        ar, br = a.resolve(strict=True), b.resolve(strict=True)
        if ar == br or ar in br.parents or br in ar.parents:
            raise Hold('same_or_nested_path')
        if not ar.is_dir() or not br.is_dir():
            raise Hold('unsafe_root')
        # Different mount devices are not proof of an off-device backup.
        ia, ib = inventory(a), inventory(b)
        if not ia:
            raise Hold('empty_inventory')
        if ia != ib:
            raise Hold('inventory_or_hash_mismatch')
        report.update(comparison_pass=True, status='MATCH_BUT_LOCATION_UNVERIFIED',
                      file_count=len(ia), total_bytes=sum(size for _, size in ia.values()))
    except (Hold, OSError, RuntimeError) as exc:
        report.update(status='HOLD', reason=str(exc) if isinstance(exc, Hold) else 'path_unreadable')
    return report

def main() -> int:
    parser = argparse.ArgumentParser(description='Read-only backup pair comparison')
    parser.add_argument('local_backup', type=Path)
    parser.add_argument('external_backup', type=Path)
    args = parser.parse_args()
    report = compare(args.local_backup, args.external_backup)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report['comparison_pass'] else 2

if __name__ == '__main__':
    sys.exit(main())

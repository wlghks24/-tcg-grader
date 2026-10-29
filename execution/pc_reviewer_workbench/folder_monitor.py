"""Read-only polling fingerprint for local checkout freshness; NO Git fetch or write."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path

IGNORED = {'.git', '.hg', '.svn', '__pycache__', '.venv', 'venv', 'node_modules',
           '.pytest_cache', '.mypy_cache', '.ruff_cache', 'build', 'dist'}
MAX_ITEMS = 50000

class FolderMonitorHold(ValueError):
    pass


def fingerprint(folder: Path) -> dict:
    root = folder.expanduser().absolute()
    if root.is_symlink() or not root.is_dir():
        raise FolderMonitorHold('invalid_watch_folder')
    digest = hashlib.sha256()
    count = 0
    for base, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(n for n in dirs if n not in IGNORED and not (Path(base)/n).is_symlink())
        for name in sorted(names):
            p = Path(base) / name
            if p.is_symlink() or not p.is_file():
                continue
            try:
                stat = p.stat()
            except FileNotFoundError:
                raise FolderMonitorHold('folder_changed_mid_scan')
            count += 1
            if count > MAX_ITEMS:
                raise FolderMonitorHold('watch_item_limit')
            rel = p.relative_to(root).as_posix()
            digest.update(f'{rel}\0{stat.st_size}\0{stat.st_mtime_ns}\n'.encode('utf-8', 'surrogatepass'))
    return {'schema': 'tcg-pc-folder-fingerprint/v1', 'files': count,
            'fingerprint': digest.hexdigest(), 'method': 'path_size_mtime_not_content_hash'}

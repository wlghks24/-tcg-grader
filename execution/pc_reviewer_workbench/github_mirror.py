"""Opt-in isolated read-only-audit *copy* of public GitHub main; never touch user checkout."""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess

REPO_URL = 'https://github.com/wlghks24/-tcg-grader.git'
MIRROR_NAME = 'TCG_Grader_Audit_Mirror'

class MirrorHold(RuntimeError):
    pass


def _git(*args: str, cwd: Path | None = None, timeout: int = 90) -> str:
    cmd = ['git', '-c', 'core.hooksPath=/dev/null', *args]
    try:
        done = subprocess.run(cmd, cwd=cwd, text=True, encoding='utf-8', errors='replace',
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MirrorHold('git_unavailable_or_timeout') from exc
    if done.returncode != 0:
        raise MirrorHold('git_failed:' + ' '.join(args[:2]) + ':' + done.stderr[:300])
    return done.stdout.strip()


def sync_mirror(target: Path) -> dict:
    root = target.expanduser().absolute()
    if root.name != MIRROR_NAME or root.is_symlink() or any(x.is_symlink() for x in root.parents):
        raise MirrorHold('only_dedicated_audit_mirror_path_allowed')
    if not root.exists():
        if not root.parent.is_dir():
            raise MirrorHold('mirror_parent_must_exist')
        # Clone only exact public repository into a new path. No submodules, no arbitrary remote.
        _git('clone', '--no-checkout', '--single-branch', '--branch', 'main',
             REPO_URL, str(root), cwd=root.parent, timeout=180)
        _git('checkout', 'main', cwd=root)
    if not root.is_dir() or (root/'.git').is_symlink():
        raise MirrorHold('invalid_mirror')
    remote = _git('remote', 'get-url', 'origin', cwd=root)
    if remote != REPO_URL:
        raise MirrorHold('unexpected_origin_url')
    if _git('branch', '--show-current', cwd=root) != 'main':
        raise MirrorHold('mirror_must_track_main')
    if _git('status', '--porcelain', '--untracked-files=all', cwd=root):
        raise MirrorHold('mirror_has_local_changes_no_overwrite')
    before = _git('rev-parse', 'HEAD', cwd=root)
    _git('fetch', '--no-tags', 'origin', 'main', cwd=root, timeout=180)
    _git('merge', '--ff-only', 'origin/main', cwd=root)
    after = _git('rev-parse', 'HEAD', cwd=root)
    return {'status': 'MIRROR_UPDATED' if before != after else 'MIRROR_ALREADY_LATEST',
            'source': str(root), 'before': before, 'after': after, 'original_user_checkout_modified': False}


def main() -> int:
    p = argparse.ArgumentParser(description='Manually sync dedicated GitHub audit mirror')
    p.add_argument('--path', type=Path, default=Path.home()/MIRROR_NAME)
    args = p.parse_args()
    print(sync_mirror(args.path))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Exact successor of the reviewed V650 installer; no deployment authority."""
import hashlib
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = 'execution/tablet_preserved_update.py'
HISTORICAL = '140a8ae4d0d3845bc875b18ff54c631144da323c'
BASE = '78cda08b9f8bcfecc5701e773f42f5cb6108656c'
CANDIDATE = 'e613fc5cbf290b5aa3ade2612eeb3a4c1b8a1d23'
BASE_DIGEST = '9c380408d53f314a8723ff537c8fdab587fc9e3a2d9fba84dd13edf12589f4cc'
BASE_SIZE = 19397
OLD = b"    untracked_hashes = {name:digest(repo/name) for name in untracked}\n    moved_untracked = []\n    try:\n        lock_pid.write_text(str(os.getpid()), encoding='ascii')\n"
NEW = b"    untracked_hashes = {}\n    moved_untracked = []\n    try:\n        lock_pid.write_text(str(os.getpid()), encoding='ascii')\n        untracked_hashes = {name:digest(repo/name) for name in untracked}\n"


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def full_sha(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{40}', value) is not None


def git(root, *args):
    return subprocess.check_output(['git', '--no-replace-objects', *args], cwd=root, timeout=30)


def ancestor(root, older, newer):
    git(root, 'merge-base', '--is-ancestor', older, newer)


def blob(root, revision):
    row = git(root, 'ls-tree', '-z', revision, '--', INSTALLER)
    require(re.fullmatch(rb'100644 blob [0-9a-f]{40}\t' + re.escape(INSTALLER.encode()) + rb'\x00', row) is not None, 'installer not regular tracked file')
    return git(root, 'show', revision + ':' + INSTALLER)


def exact_change(original):
    require(original.count(OLD) == 1, 'unexpected installer change boundary')
    return original.replace(OLD, NEW, 1)


def _verify(root, historical, base, candidate, digest, size):
    root = Path(root)
    require(all(full_sha(x) for x in (historical, base, candidate)), 'unbound commit')
    ancestor(root, historical, base)
    require(git(root, 'rev-list', '--parents', '-n', '1', candidate).decode().split() == [candidate, base], 'incorrect candidate parent')
    ancestor(root, candidate, 'HEAD')
    require(git(root, 'diff', '--no-renames', '--name-only', '-z', base, candidate) == INSTALLER.encode() + b'\0', 'candidate changed other paths')
    original = blob(root, historical)
    require(len(original) == size and hashlib.sha256(original).hexdigest() == digest, 'historical digest mismatch')
    require(blob(root, base) == original, 'unreviewed base installer')
    expected = exact_change(original)
    require(blob(root, candidate) == expected, 'unexpected candidate bytes')
    require(blob(root, 'HEAD') == expected, 'committed installer changed')
    target = root / INSTALLER
    require(not (root / 'execution').is_symlink() and not target.is_symlink() and target.is_file(), 'unsafe live path')
    require(target.read_bytes() == expected, 'live installer changed')
    return original


def validate_installer_lock_successor(prior_digest):
    require(prior_digest == BASE_DIGEST, 'incorrect V650 predecessor pin')
    _verify(ROOT, HISTORICAL, BASE, CANDIDATE, BASE_DIGEST, BASE_SIZE)
    return INSTALLER


def _scope(visible, source, head, prior_head, root, historical, base, candidate, digest, size):
    # Only hide this exact later path, never a historical or non-HEAD change.
    if INSTALLER not in visible or head != 'HEAD' or not full_sha(source):
        return visible
    try:
        original = _verify(root, historical, base, candidate, digest, size)
        ancestor(root, source, base)
        require(blob(root, source) == original, 'earlier change remains visible')
        if prior_head not in (None, 'HEAD'):
            require(full_sha(prior_head), 'unbound earlier boundary')
            ancestor(root, source, prior_head)
            ancestor(root, prior_head, base)
            require(blob(root, prior_head) == original, 'earlier boundary changed installer')
        return [path for path in visible if path != INSTALLER]
    except (AssertionError, OSError, ValueError, subprocess.SubprocessError):
        return visible


def preserve_reviewed_installer_lock_scope(visible, source, head='HEAD', *, prior_head=None):
    return _scope(visible, source, head, prior_head, ROOT, HISTORICAL, BASE, CANDIDATE, BASE_DIGEST, BASE_SIZE)

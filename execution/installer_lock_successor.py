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
ANDROID = 'ANDROID_UPDATE_AND_START.sh'
IGNORE_TRANSITION = (
    'd2d3211bfb7dd997445e552de216c73f7a472169',
    'c6883ba25b8d7b941342f77a8bcc2f4e13ef2001',
    '1a18b6ceb135cc660d258b26463437bc0e83bce2',
    '4c924206b41e4b7c57bb0a444cdfc9b883d413dc87ef5ecfb3799fdbef7377c8',
    20281,
)
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


def blob(root, revision, path=INSTALLER):
    row = git(root, 'ls-tree', '-z', revision, '--', path)
    require(re.fullmatch(rb'100644 blob [0-9a-f]{40}\t' + re.escape(path.encode()) + rb'\x00', row) is not None, 'updater not regular tracked file')
    return git(root, 'show', revision + ':' + path)


def exact_change(original):
    require(original.count(OLD) == 1, 'unexpected installer change boundary')
    return original.replace(OLD, NEW, 1)


def guarded_bytes(path, original):
    if path == INSTALLER:
        edits = [(b"git(repo, 'merge', '--ff-only', target, timeout=180)",
                  b"git(repo, 'merge', '--ff-only', '--no-overwrite-ignore', target, timeout=180)")]
    elif path == ANDROID:
        edits = [(b'git merge --ff-only "$TARGET_MAIN_SHA"', b'git merge --ff-only --no-overwrite-ignore "$TARGET_MAIN_SHA"'),
                 (b'git merge --ff-only origin/main', b'git merge --ff-only --no-overwrite-ignore origin/main')]
    else:
        raise AssertionError('unknown updater path')
    for old, new in edits:
        require(original.count(old) == 1, 'unexpected ignored-file edit boundary')
        original = original.replace(old, new, 1)
    return original


def verify_live(root, path, expected):
    require(blob(root, 'HEAD', path) == expected, 'committed updater changed')
    target = root / path
    require(all(not (root / Path(*Path(path).parts[:i])).is_symlink()
                for i in range(1, len(Path(path).parts)+1)) and target.is_file(), 'unsafe live path')
    require(target.read_bytes() == expected, 'live updater changed')


def verify_ignore_transition(root, lock_candidate, lock_bytes, transition):
    base, candidate, historical, digest, size = transition
    require(all(full_sha(x) for x in (base, candidate, historical)), 'unbound ignored-file commit')
    ancestor(root, lock_candidate, base)
    ancestor(root, historical, base)
    require(git(root, 'rev-list', '--parents', '-n', '1', candidate).decode().split() == [candidate, base], 'incorrect ignored-file parent')
    ancestor(root, candidate, 'HEAD')
    paths = (ANDROID, INSTALLER)
    require(git(root, 'diff', '--no-renames', '--name-only', '-z', base, candidate) == b''.join(p.encode()+b'\0' for p in paths), 'unexpected ignored-file candidate paths')
    shell = blob(root, historical, ANDROID)
    require(len(shell) == size and hashlib.sha256(shell).hexdigest() == digest, 'historical Android digest mismatch')
    for path, original in ((INSTALLER, lock_bytes), (ANDROID, shell)):
        require(blob(root, base, path) == original, 'unreviewed ignored-file base')
        expected = guarded_bytes(path, original)
        require(blob(root, candidate, path) == expected, 'unexpected ignored-file candidate bytes')
        if path == INSTALLER and transition == IGNORE_TRANSITION:
            from execution.installer_runtime_successor import validate_runtime_successor
            validate_runtime_successor(root, candidate, expected)
        else:
            verify_live(root, path, expected)


def _verify(root, historical, base, candidate, digest, size, ignore_transition=None):
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
    if ignore_transition is None:
        verify_live(root, INSTALLER, expected)
    else:
        verify_ignore_transition(root, candidate, expected, ignore_transition)
    return original


def validate_installer_lock_successor(prior_digest):
    require(prior_digest == BASE_DIGEST, 'incorrect V650 predecessor pin')
    _verify(ROOT, HISTORICAL, BASE, CANDIDATE, BASE_DIGEST, BASE_SIZE, IGNORE_TRANSITION)
    return INSTALLER


def validate_android_ignore_successor(prior_digest):
    require(prior_digest == IGNORE_TRANSITION[3], 'incorrect V1011 predecessor pin')
    validate_installer_lock_successor(BASE_DIGEST)
    return ANDROID


def _scope(visible, source, head, prior_head, root, historical, base, candidate, digest, size, ignore_transition=None):
    # Only hide this exact later path, never a historical or non-HEAD change.
    if INSTALLER not in visible or head != 'HEAD' or not full_sha(source):
        return visible
    try:
        original = _verify(root, historical, base, candidate, digest, size, ignore_transition)
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
    return _scope(visible, source, head, prior_head, ROOT, HISTORICAL, BASE, CANDIDATE, BASE_DIGEST, BASE_SIZE, IGNORE_TRANSITION)

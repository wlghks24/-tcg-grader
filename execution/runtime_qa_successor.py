"""Exact reviewed successor for the shared Android runtime QA marker contract."""
import hashlib
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
NAME = 'tablet_runtime_qa.py'
BASE = '4d77be70e2c1fdf93d8f319e8c59814c9aa48c9f'
CANDIDATE = '471201ea81aa80366cbe9fd4f5a8ffee7f11ec84'
OLD_DIGEST = 'bb5f0576593a407d8e0d9a26a255d12ea6c0a390304c8fd538c204f68abc82a6'
OLD_SIZE = 3653
PATHS = ('.github/workflows/android-updater-guard.yml', 'integrity_manifest.json', NAME,
         'test_tablet_manifest_target_race_v273.py', 'test_tablet_standalone_hardening_v209.py')
OLD = b'    "git merge --ff-only origin/main",\n'
NEW = (b'    "git merge --ff-only --no-overwrite-ignore origin/main",\n'
       b'    \'git merge --ff-only --no-overwrite-ignore "$TARGET_MAIN_SHA"\',\n')


def require(ok, label):
    if not ok:
        raise AssertionError(label)


def full_sha(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{40}', value) is not None


def git(root, *args):
    return subprocess.check_output(['git', '--no-replace-objects', *args], cwd=root, timeout=30, stderr=subprocess.PIPE)


def ancestor(root, source, target):
    git(root, 'merge-base', '--is-ancestor', source, target)


def blob(root, rev):
    row = git(root, 'ls-tree', '-z', rev, '--', NAME)
    require(re.fullmatch(rb'100644 blob [0-9a-f]{40}\t' + NAME.encode() + rb'\x00', row) is not None, 'QA not regular tracked file')
    return git(root, 'show', rev + ':' + NAME)


def exact_change(old):
    require(old.count(OLD) == 1, 'unexpected QA marker boundary')
    return old.replace(OLD, NEW, 1)


def verify(root, base, candidate, digest, size):
    require(full_sha(base) and full_sha(candidate), 'unbound QA proof commits')
    require(git(root, 'rev-list', '--parents', '-n', '1', candidate).decode().split() == [candidate, base], 'wrong QA candidate parent')
    ancestor(root, candidate, 'HEAD')
    require(git(root, 'diff', '--no-renames', '--name-only', '-z', base, candidate) == b''.join(p.encode()+b'\0' for p in PATHS), 'unexpected QA candidate paths')
    old = blob(root, base)
    require(len(old) == size and hashlib.sha256(old).hexdigest() == digest, 'wrong QA baseline digest')
    new = exact_change(old)
    require(blob(root, candidate) == new, 'unreviewed QA candidate bytes')
    require(blob(root, 'HEAD') == new, 'unreviewed committed QA bytes')
    target = root / NAME
    require(not target.is_symlink() and target.is_file() and target.read_bytes() == new, 'unreviewed live QA bytes')
    return old


def _scope(visible, source, head, prior_head, root, base, candidate, digest, size):
    if NAME not in visible or head != 'HEAD' or not full_sha(source):
        return visible
    try:
        ancestor(root, source, base)
        old = verify(root, base, candidate, digest, size)
        require(blob(root, source) == old, 'earlier QA change must remain visible')
        if prior_head not in (None, 'HEAD'):
            require(full_sha(prior_head), 'unbound QA boundary')
            ancestor(root, source, prior_head)
            ancestor(root, prior_head, base)
            require(blob(root, prior_head) == old, 'earlier QA boundary differs')
        return [p for p in visible if p != NAME]
    except (AssertionError, OSError, ValueError, subprocess.SubprocessError):
        return visible


def preserve_reviewed_runtime_qa_scope(visible, source, head='HEAD', *, prior_head=None):
    return _scope(visible, source, head, prior_head, ROOT, BASE, CANDIDATE, OLD_DIGEST, OLD_SIZE)

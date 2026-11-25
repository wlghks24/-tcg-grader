"""Exact reviewed transition for deferred-publisher baseline pin validation."""
import hashlib
from pathlib import Path
import subprocess

NAME = 'execution/deferred_publish_tree.py'
BASE = '848a1234f03bc18e175276bb568eda3d89878cd6'
CANDIDATE = 'b4d3f789e08fe827ea552919f428b560cc0b540c'
OLD = ('8aa49e18c7a6c49cd947c932fe29723ac4f8af96427c867e2ccf3f3316d01031', 5590)
NEW = ('26d5cee11af4de6774e935f71c3ef1b971d785ebd6ab209ced5ef7c4ace4b2e5', 6264)
PATHS = (NAME, 'execution/tests/test_deferred_publish_base_pin.py', 'integrity_manifest.json')


def require(ok, reason):
    if not ok:
        raise AssertionError(reason)


def git(root, *args):
    return subprocess.check_output(['git', '--no-replace-objects', *args], cwd=root, timeout=30)


def pinned(root, ref, pin):
    entry = git(root, 'ls-tree', '-z', ref, '--', NAME)
    raw = git(root, 'show', ref + ':' + NAME)
    oid = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    require(entry == ('100644 blob ' + oid + '\t' + NAME + '\0').encode(), 'unsafe tree entry')
    require((hashlib.sha256(raw).hexdigest(), len(raw)) == pin, 'incorrect source pin')
    return raw


def verify(root, previous, base=BASE, candidate=CANDIDATE, old=OLD, new=NEW, paths=PATHS):
    root = Path(root)
    require(git(root, 'rev-list', '--parents', '-n', '1', candidate).decode().split() == [candidate, base], 'wrong successor parent')
    git(root, 'merge-base', '--is-ancestor', candidate, 'HEAD')
    expected = b''.join(p.encode() + b'\0' for p in sorted(paths))
    require(git(root, 'diff', '--no-renames', '--name-only', '-z', base, candidate) == expected, 'unexpected successor paths')
    require(pinned(root, base, old) == previous, 'wrong historical source')
    reviewed = pinned(root, candidate, new)
    require(pinned(root, 'HEAD', new) == reviewed, 'unreviewed committed successor')
    path = root / NAME
    require(all(not root.joinpath(*Path(NAME).parts[:i]).is_symlink() for i in range(1, len(Path(NAME).parts)+1)) and path.is_file(), 'unsafe live path')
    require(path.read_bytes() == reviewed, 'unreviewed live successor')
    return reviewed

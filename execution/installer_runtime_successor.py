"""Exact runtime-safety successor of the reviewed ignored-file installer."""
import hashlib
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
NAME = 'execution/tablet_preserved_update.py'
BASE = 'b97706da88418ccf69f9c95da8cc7ef7eb72a411'
CANDIDATE = '1bff69c7349b29290d0bf683865bf964def4e892'
OLD = ('acc62d9fc048178f43f13acf15ff31f9ac5ca689649be30744c7011bfb30676a', 19452)
NEW = ('8d20249980d13ea7b1bb3cdd7a3ec4c331797008019622fe03f953eda7b3418c', 21072)


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def git(root, *args):
    return subprocess.check_output(['git', '--no-replace-objects', *args], cwd=root, timeout=30)


def blob(root, ref):
    row = git(root, 'ls-tree', '-z', ref, '--', NAME)
    require(re.fullmatch(rb'100644 blob [0-9a-f]{40}\t' + NAME.encode().replace(b'.', rb'\.') + b'\x00', row) is not None,
            'unsafe installer tree entry')
    return git(root, 'show', ref + ':' + NAME)


def pin(raw, expected):
    return (hashlib.sha256(raw).hexdigest(), len(raw)) == expected


def _verify(root, previous, previous_bytes, base, candidate, old_pin, new_pin, successor=None):
    root = Path(root)
    require(all(isinstance(s, str) and re.fullmatch(r'[0-9a-f]{40}', s) for s in (previous, base, candidate)), 'unbound commit')
    git(root, 'merge-base', '--is-ancestor', previous, base)
    git(root, 'merge-base', '--is-ancestor', candidate, 'HEAD')
    require(git(root, 'rev-list', '--parents', '-n', '1', candidate).decode().split() == [candidate, base], 'wrong successor parent')
    require(git(root, 'diff', '--no-renames', '--name-only', '-z', base, candidate) == NAME.encode()+b'\0', 'unexpected successor paths')
    require(blob(root, previous) == blob(root, base) == previous_bytes and pin(previous_bytes, old_pin), 'unreviewed predecessor')
    current = blob(root, candidate)
    require(pin(current, new_pin), 'unreviewed candidate installer')
    if successor is not None:
        next_base, next_candidate, next_pin = successor
        _verify(root, candidate, current, next_base, next_candidate, new_pin, next_pin)
        return previous_bytes
    require(blob(root, 'HEAD') == current, 'unreviewed committed installer')
    path = root / NAME
    require(all(not root.joinpath(*Path(NAME).parts[:i]).is_symlink() for i in range(1, len(Path(NAME).parts)+1)) and path.is_file(), 'unsafe live installer')
    require(path.read_bytes() == current, 'unreviewed live installer')
    return previous_bytes


def validate_runtime_successor(root, previous, previous_bytes):
    successor = None
    if blob(root, 'HEAD') != blob(root, CANDIDATE):
        successor = ('65faabb229c0fa35b5e577bbe7d21f5f167a6575',
                     '4485de6dfb40fcf1c4ea401cc9a0ef3f4736e50e',
                     ('6c2f9a50afdc9bf586da2044fec8f8ddcfc70b28e808b5ff2954b2f92ebc7e72', 21572))
    return _verify(root, previous, previous_bytes, BASE, CANDIDATE, OLD, NEW, successor)


def historical_installer_bytes(root=ROOT):
    # Verify the original lock/ignored-file chain AND current successor before
    # executing the historical fixture. Never select arbitrary historical code.
    from execution.installer_lock_successor import BASE_DIGEST, validate_installer_lock_successor
    require(Path(root).resolve() == ROOT.resolve(), 'unexpected historical root')
    validate_installer_lock_successor(BASE_DIGEST)
    raw = blob(root, BASE)
    require(pin(raw, OLD), 'historical installer pin mismatch')
    return raw

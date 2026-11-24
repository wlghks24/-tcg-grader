"""Exact V645 installer regression successor; never confers deployment authority."""
import hashlib
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
NAME = 'execution/tests/test_tablet_preserved_update.py'
MANIFEST = 'integrity_manifest.json'
HISTORICAL = '76f42981bda20f76cf5b935b1ebab8f511399761'
BASE = 'b97706da88418ccf69f9c95da8cc7ef7eb72a411'
TRANSITIONS = (
    ('68cd221145f2fc549b5fc4b12574bceb4051eebb',
     '6efb36ee18cd5f4c979b452faa7c0717e0108fc1', (NAME,)),
    ('84b8249cc7c4101af935eb4055e7242a6f1e8865',
     'b6556baa03b1896d0fffc890da8495500ae8e6b5', (NAME, MANIFEST)),
)
PINS = (
    ('156f59bc777f5311e03b88cbef19e4509d246a05e343f6d49ef952f80c165937', 15453, '0c8f1f864bd65907d3b9e954f667329af2d88e4c'),
    ('a97afe288f4a713430daa382269d2d6ca0514c770d6248f0330906a2a29e3d3a', 16925, '32572f7c82f7c2a10d3f972fdba8fc2adee46d10'),
    ('7f58bf8a9811d968d0e39c868ae9a16944409531e38459481c313d6a151822e5', 17267, 'd797af6ea708d0eb880a84572322e86bf33df20e'),
)


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def git(root, *args):
    return subprocess.check_output(['git', '--no-replace-objects', *args], cwd=root, timeout=30)


def pinned(root, revision, pin):
    digest, size, blob = pin
    require(git(root, 'ls-tree', '-z', revision, '--', NAME) ==
            ('100644 blob ' + blob + '\t' + NAME + '\0').encode(), 'unexpected test tree entry')
    raw = git(root, 'show', revision + ':' + NAME)
    require(len(raw) == size and hashlib.sha256(raw).hexdigest() == digest, 'unreviewed test bytes')
    return raw


def _verify(root, historical, base, transitions, pins):
    root = Path(root)
    require(len(transitions) == 2 and len(pins) == 3, 'invalid transition count')
    revisions = (historical, base) + tuple(s for step in transitions for s in step[:2])
    require(all(isinstance(s, str) and re.fullmatch(r'[0-9a-f]{40}', s) for s in revisions), 'unbound revision')
    git(root, 'merge-base', '--is-ancestor', historical, base)
    original = pinned(root, historical, pins[0])
    require(pinned(root, base, pins[0]) == original, 'unreviewed baseline')
    previous, expected = base, original
    for i, (parent, candidate, paths) in enumerate(transitions):
        git(root, 'merge-base', '--is-ancestor', previous, parent)
        require(pinned(root, parent, pins[i]) == expected, 'unreviewed intermediate parent')
        require(git(root, 'rev-list', '--parents', '-n', '1', candidate).decode().split() ==
                [candidate, parent], 'unexpected transition parent')
        actual = git(root, 'diff', '--no-renames', '--name-only', '-z', parent, candidate)
        require(actual == b''.join(path.encode()+b'\0' for path in sorted(paths)), 'unexpected transition paths')
        expected = pinned(root, candidate, pins[i+1])
        previous = candidate
    git(root, 'merge-base', '--is-ancestor', previous, 'HEAD')
    require(pinned(root, 'HEAD', pins[-1]) == expected, 'unreviewed committed test')
    path = root / NAME
    require(all(not root.joinpath(*Path(NAME).parts[:i]).is_symlink()
                for i in range(1, len(Path(NAME).parts)+1)) and path.is_file(), 'unsafe live test')
    require(path.read_bytes() == expected, 'unreviewed live test')
    return NAME


def validate_installer_test_successor(prior_digest):
    require(prior_digest == PINS[0][0], 'incorrect historical V645 test pin')
    return _verify(ROOT, HISTORICAL, BASE, TRANSITIONS, PINS)


def _scope(visible, source, head, prior_head, root, historical, base, transitions, pins):
    """Delegate only an exact later test transition from an unchanged source."""
    if NAME not in visible or head != 'HEAD' or prior_head not in (None, 'HEAD'):
        return visible
    if not isinstance(source, str) or not re.fullmatch(r'[0-9a-f]{40}', source):
        return visible
    try:
        git(root, 'merge-base', '--is-ancestor', historical, source)
        git(root, 'merge-base', '--is-ancestor', source, base)
        original = pinned(root, historical, pins[0])
        require(pinned(root, source, pins[0]) == original, 'earlier test change remains visible')
        require(_verify(root, historical, base, transitions, pins) == NAME, 'successor unverified')
        return [name for name in visible if name != NAME]
    except (AssertionError, OSError, ValueError, subprocess.SubprocessError):
        return visible


def preserve_reviewed_installer_test_scope(visible, source, head='HEAD', *, prior_head=None):
    return _scope(visible, source, head, prior_head, ROOT, HISTORICAL, BASE, TRANSITIONS, PINS)

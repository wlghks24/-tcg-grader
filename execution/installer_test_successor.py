"""Exact V645 installer regression successor; never confers deployment authority."""
import hashlib
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
NAME = 'execution/tests/test_tablet_preserved_update.py'
MANIFEST = 'integrity_manifest.json'
GRAPHIFY_NAME = 'execution/tests/test_graphify_preserved_update_v648.py'
HISTORICAL = '76f42981bda20f76cf5b935b1ebab8f511399761'
BASE = 'b97706da88418ccf69f9c95da8cc7ef7eb72a411'
TRANSITIONS = (
    ('68cd221145f2fc549b5fc4b12574bceb4051eebb',
     '6efb36ee18cd5f4c979b452faa7c0717e0108fc1', (NAME,)),
    ('84b8249cc7c4101af935eb4055e7242a6f1e8865',
     'b6556baa03b1896d0fffc890da8495500ae8e6b5', (NAME, MANIFEST)),
    ('356cb6b72f43462885b0305b673f9aa5047d9a11',
     '681cf745e6c16bf2162a5d157a5c1c38699e4919', (NAME,)),
    ('6fbb565d04e71e7cfa070e85f75c17f30e5970c1',
     '800353159134636e030fdff5323dffde81b106da', (NAME,)),
)
PINS = (
    ('156f59bc777f5311e03b88cbef19e4509d246a05e343f6d49ef952f80c165937', 15453, '0c8f1f864bd65907d3b9e954f667329af2d88e4c'),
    ('a97afe288f4a713430daa382269d2d6ca0514c770d6248f0330906a2a29e3d3a', 16925, '32572f7c82f7c2a10d3f972fdba8fc2adee46d10'),
    ('7f58bf8a9811d968d0e39c868ae9a16944409531e38459481c313d6a151822e5', 17267, 'd797af6ea708d0eb880a84572322e86bf33df20e'),
    ('42640ee073f30e1ac29685c617d3fa70f5e726ea30e305497e55337a1c2953b8', 18484, '3643c3674c66fa787f7c074bca36e49480a68b60'),
    ('6182f32fbf30d521f88686c7609747f78870dbd23e0585508072c00196cc8b7c', 19616, '576abcb378a56845c9bc7ce7c7a61e014e42c5c9'),
)


def require(ok, message):
    if not ok:
        raise AssertionError(message)


def git(root, *args):
    return subprocess.check_output(['git', '--no-replace-objects', *args], cwd=root, timeout=30)


def pinned(root, revision, pin, name=NAME):
    digest, size, blob = pin
    require(git(root, 'ls-tree', '-z', revision, '--', name) ==
            ('100644 blob ' + blob + '\t' + name + '\0').encode(), 'unexpected test tree entry')
    raw = git(root, 'show', revision + ':' + name)
    require(len(raw) == size and hashlib.sha256(raw).hexdigest() == digest, 'unreviewed test bytes')
    return raw


def _verify(root, historical, base, transitions, pins, *, name=NAME):
    root = Path(root)
    require(name in (NAME, GRAPHIFY_NAME), 'unreviewed test path')
    counts = (1,) if name == GRAPHIFY_NAME else (2, 4)
    require(len(transitions) in counts and len(pins) == len(transitions) + 1, 'invalid transition count')
    revisions = (historical, base) + tuple(s for step in transitions for s in step[:2])
    require(all(isinstance(s, str) and re.fullmatch(r'[0-9a-f]{40}', s) for s in revisions), 'unbound revision')
    git(root, 'merge-base', '--is-ancestor', historical, base)
    original = pinned(root, historical, pins[0], name)
    require(pinned(root, base, pins[0], name) == original, 'unreviewed baseline')
    previous, expected = base, original
    for i, (parent, candidate, paths) in enumerate(transitions):
        git(root, 'merge-base', '--is-ancestor', previous, parent)
        require(pinned(root, parent, pins[i], name) == expected, 'unreviewed intermediate parent')
        require(git(root, 'rev-list', '--parents', '-n', '1', candidate).decode().split() ==
                [candidate, parent], 'unexpected transition parent')
        actual = git(root, 'diff', '--no-renames', '--name-only', '-z', parent, candidate)
        require(actual == b''.join(path.encode()+b'\0' for path in sorted(paths)), 'unexpected transition paths')
        expected = pinned(root, candidate, pins[i+1], name)
        previous = candidate
    git(root, 'merge-base', '--is-ancestor', previous, 'HEAD')
    require(pinned(root, 'HEAD', pins[-1], name) == expected, 'unreviewed committed test')
    path = root / name
    require(all(not root.joinpath(*Path(name).parts[:i]).is_symlink()
                for i in range(1, len(Path(name).parts)+1)) and path.is_file(), 'unsafe live test')
    require(path.read_bytes() == expected, 'unreviewed live test')
    return name


def validate_installer_test_successor(prior_digest):
    require(prior_digest == PINS[0][0], 'incorrect historical V645 test pin')
    return _verify(ROOT, HISTORICAL, BASE, TRANSITIONS, PINS)


def _graphify_evidence():
    # Only the reviewed fixture transition may extend V648's original pin.
    pins = (
        ('489eeb78bb9996c5d63eae4647fec889be7606bfc648433d9845d954b7f0fd60', 5694, '003a3c321ee19917024286613b90596ace21a340'),
        ('55c769d51878944dbd5db74d54354bda4bf939469ef581ee2a340055feb6cf99', 6295, '5ac354e24e84e61e193e0b0e6978fdec0efbaece'),
    )
    return (
        '5681a936c8bbcfd5b14756d7b2cd389d3ba58fb7',
        '3d7bd024e1662a0318064420c9cd9737309c9eda',
        (('3d7bd024e1662a0318064420c9cd9737309c9eda', '9bc14dae01e95b117e69b45c12d1a067e0dc1dcd', (GRAPHIFY_NAME,)),),
        pins,
    )


def validate_graphify_test_successor(prior_digest):
    historical, base, transitions, pins = _graphify_evidence()
    require(prior_digest == pins[0][0], 'incorrect historical V648 test pin')
    return _verify(ROOT, historical, base, transitions, pins, name=GRAPHIFY_NAME)


def _scope(visible, source, head, prior_head, root, historical, base, transitions, pins, *, name=NAME):
    """Delegate only an exact later test transition from an unchanged source."""
    if name not in visible or head != 'HEAD' or prior_head not in (None, 'HEAD'):
        return visible
    if not isinstance(source, str) or not re.fullmatch(r'[0-9a-f]{40}', source):
        return visible
    try:
        git(root, 'merge-base', '--is-ancestor', historical, source)
        git(root, 'merge-base', '--is-ancestor', source, base)
        original = pinned(root, historical, pins[0], name)
        require(pinned(root, source, pins[0], name) == original, 'earlier test change remains visible')
        require(_verify(root, historical, base, transitions, pins, name=name) == name, 'successor unverified')
        return [path for path in visible if path != name]
    except (AssertionError, OSError, ValueError, subprocess.SubprocessError):
        return visible


def preserve_reviewed_installer_test_scope(visible, source, head='HEAD', *, prior_head=None):
    return _scope(visible, source, head, prior_head, ROOT, HISTORICAL, BASE, TRANSITIONS, PINS)


def preserve_reviewed_graphify_test_scope(visible, source, head='HEAD', *, prior_head=None):
    historical, base, transitions, pins = _graphify_evidence()
    return _scope(visible, source, head, prior_head, ROOT, historical, base,
                  transitions, pins, name=GRAPHIFY_NAME)

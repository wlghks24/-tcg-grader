"""Exact reviewed purchase/provider descendant. Historical pins remain immutable.

Source review only, not CI, publish, device or learning approval.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

from execution.git_validation_cache import head_validation_request
from execution.successor_git_reads_20261122 import read, immutable_source_evidence

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = json.loads(r'''{"baseline_commit":"e74ce63f9762109f9c0cd9b6d6e9cef3e0fc23c4","candidate_commit":"dde114c247f33921c703382a0a73e5304f1d435b","baseline":{"grading_company_watch.py":{"blob":"c47318b9ec5b39bc9f04688605c5fdfa580e04e5","sha256":"992eb6c302978308265f883f6d879e2f67c6364c0d5be2223c602640cfbcfcec","bytes":24628},"grading_company_watch_resilient.py":{"blob":"0352fbb6436f87e3d076596ea32a16e52a3ed2aa","sha256":"cb6df5de0b3301d7e59bc58b242ddcbc0c9a918ebd0c5849d46e8f579e5a0d10","bytes":18169},"update_purchase_sources.py":{"blob":"ed9cd0cd5f64d8bdeacbd163587da806a422d4a7","sha256":"1c0d9540f95d7c73315e46a99c1a22a04e7dbbf8574a3887dd9544b353a6c387","bytes":35428}},"files":{"grading_company_watch.py":{"blob":"c16d9baf56909af9030dca3cda83d85c7ec6d23e","sha256":"fa34030989e8a2a9815997f2ef235a350f5c4514f5b199497dbb9f3546def788","bytes":25114},"grading_company_watch_resilient.py":{"blob":"b84523c6d6a9b2924e5fc826ded862f38e0d8903","sha256":"8deea8d4fb3694b939369a711aa78199581ca061f6517d5ee5ec5d2d95d06a35","bytes":18632},"update_purchase_sources.py":{"blob":"a69731dce8dcc005a18c06ef52cca1d5bfb092f1","sha256":"9a526690f2116405b89f54e42983aaffbf718ec63435d0fa939e78a6df2ca142","bytes":36675},"execution/tests/test_purchase_provider_boundary_20261128.py":{"blob":"27cd50e32f0c3394dd4445b4d708007e07367260","sha256":"3d8a864f869a277d7ee654a303da278e3e149cd7dd9f19722ce66a3136969911","bytes":3892},"integrity_manifest.json":{"blob":"e931dc7377b9112280263dbf4442dbc636096184","sha256":"95ef42ea0574aeb72e68da5c9be22452ff6c78534851de3f1dffa815837fa284","bytes":324635}}}''')
NAMES = frozenset(EXPECTED['baseline'])
SELF = 'execution/purchase_provider_successor_20261128.py'
TEST = 'execution/tests/test_purchase_provider_successor_20261128.py'


def _live(root, name):
    path = root / name
    assert not root.is_symlink(), name
    for part in (path, *path.parents):
        if part == root:
            break
        assert not part.is_symlink(), name
    assert path.is_file(), name
    return path.read_bytes()


def _git(root, *args):
    return read(root, *args)


def _pinned(root, ref, name, pin):
    entry = ('100644 blob ' + pin['blob'] + '\t' + name + '\0').encode()
    assert _git(root, 'ls-tree', '-z', ref, '--', name) == entry, ('tree', name)
    raw = _git(root, 'show', ref + ':' + name)
    assert len(raw) == pin['bytes'], ('bytes', name)
    assert hashlib.sha256(raw).hexdigest() == pin['sha256'], ('digest', name)
    return raw


@head_validation_request(share_objects=True)
def validate_boundary_successor(name, prior_digest, *, repo=ROOT):
    root = Path(repo)
    assert root == ROOT and name in NAMES, 'unreviewed source/root'
    e = EXPECTED
    assert prior_digest == e['baseline'][name]['sha256'], 'incorrect historical digest'
    reader = lambda *args: _git(root, *args)
    pinned = lambda ref, path, pin: _pinned(root, ref, path, pin)
    rows = immutable_source_evidence(root, e, reader, pinned)
    reader('merge-base', '--is-ancestor', e['candidate_commit'], 'HEAD')
    raw_manifest = _live(root, 'integrity_manifest.json')
    assert raw_manifest == reader('show', 'HEAD:integrity_manifest.json'), 'uncommitted manifest'
    manifest = json.loads(raw_manifest)['files']
    for path, pin in e['files'].items():
        if path == 'integrity_manifest.json':
            continue
        assert _live(root, path) == rows[path] == pinned('HEAD', path, pin), ('unreviewed live source', path)
        assert manifest[path] == {'bytes': pin['bytes'], 'sha256': pin['sha256']}, ('manifest', path)
    for path in (SELF, TEST):
        raw = _live(root, path)
        assert raw == reader('show', 'HEAD:' + path), ('uncommitted proof', path)
        assert manifest[path] == {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}, ('proof manifest', path)
    return True


def preserve_base_grading_scope(visible, source, head='HEAD', *, prior_head=None, repo=ROOT):
    """Only attribute a new base-watcher change when no earlier diff existed."""
    name = 'grading_company_watch.py'
    if head != 'HEAD' or name not in visible or not isinstance(source, str) or not re.fullmatch('[0-9a-f]{40}', source):
        return visible
    try:
        base = EXPECTED['baseline_commit']
        root = Path(repo)
        assert validate_boundary_successor(name, EXPECTED['baseline'][name]['sha256'], repo=root)
        _git(root, 'merge-base', '--is-ancestor', source, base)
        if _git(root, 'diff', '--no-renames', '--name-only', '-z', source, base, '--', name):
            return visible
        if prior_head not in (None, 'HEAD'):
            assert re.fullmatch('[0-9a-f]{40}', prior_head)
            _git(root, 'merge-base', '--is-ancestor', source, prior_head)
            _git(root, 'merge-base', '--is-ancestor', prior_head, base)
            if _git(root, 'diff', '--no-renames', '--name-only', '-z', source, prior_head, '--', name):
                return visible
        return [path for path in visible if path != name]
    except (AssertionError, OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        return visible

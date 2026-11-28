"""Immutable precollect source transition. No device or deployment approval."""
import hashlib
import json
from pathlib import Path
import subprocess

from execution.git_validation_cache import head_validation_request
from execution.successor_git_reads_20261122 import read, immutable_source_evidence

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = json.loads(r'''{"baseline_commit":"b0b3c43eb51f789fcf513c7bedaa175d542a64c8","candidate_commit":"7622094fbc6b1af06dcc9c6e40b35c11e02d497c","baseline":{"tcg_updater.py":{"blob":"e3667bdbb29fcb0099a59e77f6e6cc620da43f8e","sha256":"4b7985135921317c29a05198ef6594d8da2b1d896d63783365a1211d7d17226d","bytes":117628}},"files":{"tcg_updater.py":{"blob":"3006314e744bbf89a0c1192ce31d10194eea55f7","sha256":"c6a50bbdaa1ac6c3aecf2138c6a13071ec4e7e042ca5d3e85966e57dea571e52","bytes":119593},"execution/tests/test_precollect_boundary_20261129.py":{"blob":"becc5d2fe1c8352ad18a0e2566fbb4a12cd2fbfa","sha256":"891c9953091e375f1ae1697b2a98517239fe654c0b4d32474adc75b5e9489ff1","bytes":4166},"integrity_manifest.json":{"blob":"f289139f63749b76fb2377f6e1537f7f1b96de60","sha256":"240223e571974444d44a2c0a55386aa6484a50791c3903245203d1c0e6650b0a","bytes":325336}}}''')
NAME = 'tcg_updater.py'
SELF = 'execution/precollect_boundary_successor_20261129.py'


def git(*args):
    raw = read(ROOT, *args)
    if not isinstance(raw, bytes):
        raise ValueError('Git proof requires bytes')
    return raw


def pinned(ref, name, pin):
    expected = ('100644 blob ' + pin['blob'] + '\t' + name + '\0').encode()
    assert git('ls-tree', '-z', ref, '--', name) == expected, name
    raw = git('show', ref + ':' + name)
    assert len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256'], name
    return raw


def live(name):
    path = ROOT / name
    for part in (path, *path.parents):
        assert not part.is_symlink(), name
        if part == ROOT:
            break
    assert path.is_file(), name
    return path.read_bytes()


@head_validation_request(share_objects=True)
def validate_precollect_successor(name, prior_digest, *, repo=ROOT):
    e = EXPECTED
    assert Path(repo) == ROOT and name == NAME, 'unreviewed path or checkout'
    assert prior_digest == e['baseline'][NAME]['sha256'], 'wrong historical digest'
    rows = immutable_source_evidence(ROOT, e, git, pinned)
    git('merge-base', '--is-ancestor', e['candidate_commit'], 'HEAD')
    manifest_raw = live('integrity_manifest.json')
    assert git('show', 'HEAD:integrity_manifest.json') == manifest_raw
    manifest = json.loads(manifest_raw)['files']
    for path, pin in e['files'].items():
        if path == 'integrity_manifest.json':
            continue
        assert live(path) == rows[path] == pinned('HEAD', path, pin), path
        assert manifest[path] == {'bytes': pin['bytes'], 'sha256': pin['sha256']}, path
    raw = live(SELF)
    assert raw == git('show', 'HEAD:' + SELF)
    assert manifest[SELF] == {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    return True


def preserve_precollect_scope(visible, source, head='HEAD'):
    if head != 'HEAD' or NAME not in visible:
        return visible
    try:
        base = EXPECTED['baseline_commit']
        git('merge-base', '--is-ancestor', source, base)
        if git('diff', '--no-renames', '--name-only', '-z', source, base, '--', NAME):
            return visible
        if validate_precollect_successor(NAME, EXPECTED['baseline'][NAME]['sha256']):
            return [path for path in visible if path != NAME]
    except (AssertionError, OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
        pass
    return visible

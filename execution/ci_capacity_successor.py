"""Exact capacity-only successor. Historical commits and live bytes are checked separately."""
import hashlib
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALIGN = '.github/workflows/tablet-gpt-tcg-grader-main-alignment.yml'
EXHAUSTIVE = '.github/workflows/exhaustive-selfrefine-guard.yml'
BASE = '0434b7aa550db80a6ae297f120b7d2b851ccedd8'
CANDIDATE = '215c39b5878cdcb34a1994789ae9f58bf769114d'
BASE_HASHES = {
    ALIGN: '00000c8f9c1495fd1d1f2e316658ab2e082e30889d8249c1b290d57ea6079701',
    EXHAUSTIVE: 'a629a6d455591be263fbe3b97a4a00f8e44f2fcd61b42f78df428aaaaa921aa6',
}
MATRIX = b'        shard: [' + b', '.join(str(i).encode() for i in range(16)) + b']\n'


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def capacity_bytes(path, original):
    require(path in BASE_HASHES, 'unknown capacity path')
    boundary = b'  alignment:\n' if path == ALIGN else b'  exhaustive:\n'
    require(original.count(boundary) == 1, 'unexpected final job boundary')
    before, final = original.split(boundary)
    edits = [(b'        shard: [0, 1, 2, 3]\n', MATRIX)]
    if path == ALIGN:
        edits += [(b'    timeout-minutes: 10\n', b'    timeout-minutes: 45\n'),
                  (b'across four shards\n', b'across sixteen shards\n'),
                  (b'groups = [tests[i::4] for i in range(4)]\n', b'groups = [tests[i::16] for i in range(16)]\n')]
    else:
        edits += [(b'    timeout-minutes: 25\n', b'    timeout-minutes: 45\n'),
                  (b'          shard_count=4\n', b'          shard_count=16\n')]
    for old, new in edits:
        require(before.count(old) == 1, 'unexpected historical capacity token')
        before = before.replace(old, new, 1)
    return before + boundary + final


def _verify(root, base, candidate, pins):
    root = Path(root).resolve()
    require(set(pins) == set(BASE_HASHES), 'wrong pin inventory')
    require(all(re.fullmatch(r'[0-9a-f]{40}', x) for x in (base, candidate)), 'unbound commit')
    def git(*args):
        return subprocess.check_output(['git', '--no-replace-objects', *args], cwd=root, timeout=30)
    require(git('rev-list', '--parents', '-n', '1', candidate).decode().split() == [candidate, base], 'candidate parent mismatch')
    git('merge-base', '--is-ancestor', candidate, 'HEAD')
    changed = git('diff', '--no-renames', '--name-only', '-z', base, candidate).decode('utf-8').split('\0')
    require(changed[-1:] == [''] and set(changed[:-1]) == set(pins) and len(changed) == len(pins)+1, 'unexpected candidate paths')
    originals = {}
    for name, digest in pins.items():
        for ref in (base, candidate, 'HEAD'):
            require(git('ls-tree', ref, '--', name).startswith(b'100644 blob '), 'unexpected workflow mode')
        original = git('show', base + ':' + name)
        require(hashlib.sha256(original).hexdigest() == digest, 'historical workflow pin mismatch')
        expected = capacity_bytes(name, original)
        require(git('show', candidate + ':' + name) == expected, 'non-capacity candidate edit')
        target = root / name
        require(all(not (root / Path(*Path(name).parts[:i])).is_symlink() for i in range(1,len(Path(name).parts)+1)), 'symlink workflow path')
        require(target.is_file() and target.read_bytes() == expected, 'unreviewed live workflow bytes')
        require(git('show', 'HEAD:' + name) == expected, 'unreviewed committed workflow bytes')
        originals[name] = original
    return originals


def validate_capacity():
    """Return historical bytes only after proving exact successor and current live files."""
    return _verify(ROOT, BASE, CANDIDATE, BASE_HASHES)

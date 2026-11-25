"""Exact grading-data refresh proof; never grants merge or deployment authority."""
import hashlib
from pathlib import Path
import subprocess
from execution.deferred_publish_tree import verify_git_candidate, git, strict_json

NAME = 'grading_company_updates.json'
MANIFEST = 'integrity_manifest.json'
BASE = '9b96d702e128f65afc0b4ef80e288f2ab86a409c'
CANDIDATE = '89d1e10c526576a07c8d32e7b848ae6a1dc3adfe'
PREDECESSOR = 'ec7f551071c77484985e9c1af18b20ae20b36de6'
OLD = ('ded51b805ac5a248d4ed89fdb0dfd55f54c30251', '330ba080db4cc2fec44f93fadd3ac2e47228891407bc6eaaa3da7ccaaf7eebae', 55250)
NEW = ('d9816651fb93aa151cc6dba0971326757d55ba91', 'e9b0f8cee1d8a9f9bce28f342a810a886fde2468f19c06b27de2a6d7578e7f00', 53916)


def pinned(root, ref, pin):
    oid, digest, size = pin
    if git(root, 'ls-tree', '-z', ref, '--', NAME) != ('100644 blob '+oid+'\t'+NAME+'\0').encode():
        raise ValueError('grading tree pin mismatch')
    raw = git(root, 'show', ref+':'+NAME)
    if (hashlib.sha256(raw).hexdigest(), len(raw)) != (digest, size):
        raise ValueError('grading data pin mismatch')
    return raw


def verify(root, *, base=BASE, candidate=CANDIDATE, predecessor=PREDECESSOR, old=OLD, new=NEW):
    root = Path(root).resolve(strict=True)
    git(root, 'merge-base', '--is-ancestor', predecessor, base)
    git(root, 'merge-base', '--is-ancestor', candidate, 'HEAD')
    if pinned(root, predecessor, old) != pinned(root, base, old):
        raise ValueError('grading predecessor drift')
    verify_git_candidate(root, 'grading', base, candidate, (NAME, MANIFEST))
    reviewed = pinned(root, candidate, new)
    if pinned(root, 'HEAD', new) != reviewed:
        raise ValueError('unreviewed grading HEAD')
    for name in (NAME, MANIFEST):
        path = root/name
        if path.is_symlink() or not path.is_file() or path.read_bytes() != git(root, 'show', 'HEAD:'+name):
            raise ValueError('unreviewed live grading evidence')
    row = strict_json((root/MANIFEST).read_bytes())['files'][NAME]
    if row != {'sha256':new[1], 'bytes':new[2]}:
        raise ValueError('current grading manifest pin mismatch')
    return new[0]


def verified_blob(root):
    """Unrecognized or unverified refresh stays visible to old sync guards."""
    try:
        return verify(root)
    except (ValueError, OSError, TypeError, KeyError, subprocess.SubprocessError):
        return None

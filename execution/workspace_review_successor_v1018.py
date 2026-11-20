"""Exact reviewed UI/FX descendant; old source proofs remain immutable."""
import hashlib
import json
from pathlib import Path
import subprocess
from execution.git_validation_cache import git_validation_output
ROOT=Path(__file__).resolve().parents[1]


def _read_live_head_blobs(paths):
    """Read every current HEAD blob in one fresh Git process, never memoized.

    Keep exact bytes and failure semantics: this is not a proof-acceptance cache.
    """
    names = tuple(paths)
    assert names and len(names) == len(set(names))
    assert all(isinstance(name, str) and name and not any(
        mark in name for mark in ("\n", "\r", "\x00")
    ) for name in names), "unparseable reviewed HEAD path"
    request = "".join("HEAD:" + name + "\n" for name in names).encode("utf-8")
    raw = subprocess.run(
        ["git", "cat-file", "--batch"],
        input=request, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        cwd=ROOT, check=True, timeout=30,
    ).stdout
    assert isinstance(raw, bytes) and len(raw) <= 8 * 1024 * 1024, "oversized HEAD batch"
    cursor = 0
    verified = {}
    for name in names:
        end = raw.find(b"\n", cursor)
        assert end >= 0, "missing HEAD blob header"
        parts = raw[cursor:end].split(b" ")
        assert (len(parts) == 3 and len(parts[0]) == 40
                and all(value in b"0123456789abcdef" for value in parts[0])
                and parts[1] == b"blob" and parts[2]
                and all(48 <= value <= 57 for value in parts[2])), "invalid HEAD blob header"
        length = int(parts[2])
        assert 0 <= length <= 2 * 1024 * 1024, "oversized HEAD blob"
        start = end + 1
        stop = start + length
        assert stop < len(raw) and raw[stop:stop + 1] == b"\n", "truncated HEAD blob"
        verified[name] = raw[start:stop]
        cursor = stop + 1
    assert cursor == len(raw), "unrequested HEAD output"
    return verified


EXPECTED={'schema': 'tcg-workspace-review/v1018', 'baseline_commit': '19bf209fc6531de05903dc06baafcd10d98d4a30', 'candidate_commit': 'd1a42aae3a61827e4c6438ab850526e8ac437971', 'files': {'execution/tablet_event_summary_v890.py': {'before_sha256': '22078c19bec6a7681d44111477defb133b361e295ca393773dcb69b29e226370', 'sha256': '3f655b09b9cb07f161aa44b64d73ea73437a9c189083a82d2896a7703c531030', 'bytes': 8372}, 'execution/tablet_menu_shell_v903.js': {'before_sha256': 'b3f2611225af353fab7769b0aa2746d24343eae52cd1c6657da20f32350dc69a', 'sha256': '5960c623288904cb9794a988d47e6ecec99ff9a31d5be28704bfc2dba3d5e49e', 'bytes': 24315}, 'execution/tablet_menu_shell_v903.py': {'before_sha256': '458c642836a17c32a13fd6f23979ca4294e1522f0653d31b2c32270e601be20e', 'sha256': 'e9e90eabc1f77cc065209b3d4ba9f4cfb7fd12f4b19bf5895ab0477a999e9d0c', 'bytes': 30170}, 'index.html': {'before_sha256': '2dfeb27532f9b8ff6c6ce1761fa523d10175c73c862c715ab51bf71b60a86aeb', 'sha256': '3fd90dc27a100060132cbffd265ae53c2b901c0c0f662c4315195c6ee2f19175', 'bytes': 352120}, 'verify_browser_runtime.js': {'before_sha256': 'b844c5440313ba10a229dce18355e5055ba1571d69516f6b8349af3017777beb', 'sha256': 'f5f91d6e2987ba6caf02c828e3d7ee633fe71b71879797d90697f06ce05cd852', 'bytes': 29519}}, 'physical_tablet_verified': False, 'runtime_data_modified': False}

def validate_workspace_review_v1018(name, prior_digest=None):
    # Preserve the v1018 historical proof while accepting one separately pinned
    # descendant of the original v1017 tablet UI source.
    if name == 'execution/tablet_unified_ui_v890.py':
        from execution.workspace_review_event_region_v20261118 import validate_event_region_successor
        return validate_event_region_successor(name, prior_digest=prior_digest)
    assert name in EXPECTED['files']
    assert prior_digest in (None,EXPECTED['files'][name]['before_sha256'])
    p=ROOT/'.github/tablet-autonomy/workspace_review_v1018.json'
    assert p.is_file() and not p.is_symlink()
    assert json.loads(p.read_text())==EXPECTED
    def git(*a):
        # Share only exact immutable Git reads with the existing bounded,
        # executor-aware cache. Moving HEAD remains a live subprocess call.
        return git_validation_output(['git', *a], cwd=ROOT, timeout=30)
    base,candidate=EXPECTED['baseline_commit'],EXPECTED['candidate_commit']
    git('merge-base','--is-ancestor',base,candidate)
    git('merge-base','--is-ancestor',candidate,'HEAD')
    # The equivalent exact SHA..SHA form is eligible for the config-bound
    # immutable diff cache; do not change rename or quoting behavior.
    assert git('diff','--name-only',base+'..'+candidate).decode().splitlines()==sorted(EXPECTED['files'])
    historical = {}
    for path,pin in EXPECTED['files'].items():
        before=git('show',base+':'+path);raw=git('show',candidate+':'+path)
        assert hashlib.sha256(before).hexdigest()==pin['before_sha256']
        assert hashlib.sha256(raw).hexdigest()==pin['sha256'] and len(raw)==pin['bytes']
        historical[path] = raw
    # One live Git process reads all five HEAD blobs every validation call.
    # Unlike fixed-SHA history, neither HEAD objects nor worktree acceptance
    # is cached. A malformed or incomplete batch is an explicit failure.
    head = _read_live_head_blobs(EXPECTED['files'])
    for path,raw in historical.items():
        current=ROOT/path
        assert current.is_file() and not current.is_symlink()
        assert current.read_bytes()==raw==head[path]
    for path in ('main','.github/tablet-autonomy/workspace_restore_v1017.json','.github/tablet-autonomy/deployment_repairs_successor_v1001.json'):
        assert (ROOT/path).read_bytes()==git('show',base+':'+path)
    return True

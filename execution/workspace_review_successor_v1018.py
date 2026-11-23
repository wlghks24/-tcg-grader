"""Exact reviewed UI/FX descendant; old source proofs remain immutable."""
from execution.git_validation_cache import head_validation_request
from execution.successor_git_reads_20261122 import read as read_git

import hashlib
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
EXPECTED={'schema': 'tcg-workspace-review/v1018', 'baseline_commit': '19bf209fc6531de05903dc06baafcd10d98d4a30', 'candidate_commit': 'd1a42aae3a61827e4c6438ab850526e8ac437971', 'files': {'execution/tablet_event_summary_v890.py': {'before_sha256': '22078c19bec6a7681d44111477defb133b361e295ca393773dcb69b29e226370', 'sha256': '3f655b09b9cb07f161aa44b64d73ea73437a9c189083a82d2896a7703c531030', 'bytes': 8372}, 'execution/tablet_menu_shell_v903.js': {'before_sha256': 'b3f2611225af353fab7769b0aa2746d24343eae52cd1c6657da20f32350dc69a', 'sha256': '5960c623288904cb9794a988d47e6ecec99ff9a31d5be28704bfc2dba3d5e49e', 'bytes': 24315}, 'execution/tablet_menu_shell_v903.py': {'before_sha256': '458c642836a17c32a13fd6f23979ca4294e1522f0653d31b2c32270e601be20e', 'sha256': 'e9e90eabc1f77cc065209b3d4ba9f4cfb7fd12f4b19bf5895ab0477a999e9d0c', 'bytes': 30170}, 'index.html': {'before_sha256': '2dfeb27532f9b8ff6c6ce1761fa523d10175c73c862c715ab51bf71b60a86aeb', 'sha256': '3fd90dc27a100060132cbffd265ae53c2b901c0c0f662c4315195c6ee2f19175', 'bytes': 352120}, 'verify_browser_runtime.js': {'before_sha256': 'b844c5440313ba10a229dce18355e5055ba1571d69516f6b8349af3017777beb', 'sha256': 'f5f91d6e2987ba6caf02c828e3d7ee633fe71b71879797d90697f06ce05cd852', 'bytes': 29519}}, 'physical_tablet_verified': False, 'runtime_data_modified': False}

@head_validation_request()
def validate_workspace_review_v1018(name, prior_digest=None):
    assert name in EXPECTED['files']
    assert prior_digest in (None,EXPECTED['files'][name]['before_sha256'])
    p=ROOT/'.github/tablet-autonomy/workspace_review_v1018.json'
    assert p.is_file() and not p.is_symlink()
    assert json.loads(p.read_text())==EXPECTED
    def git(*a):return read_git(ROOT,*a)
    base,candidate=EXPECTED['baseline_commit'],EXPECTED['candidate_commit']
    git('merge-base','--is-ancestor',base,candidate)
    git('merge-base','--is-ancestor',candidate,'HEAD')
    assert git('diff','--no-renames','--name-only',base,candidate).decode().splitlines()==sorted(EXPECTED['files'])
    for path,pin in EXPECTED['files'].items():
        before=git('show',base+':'+path);raw=git('show',candidate+':'+path)
        assert hashlib.sha256(before).hexdigest()==pin['before_sha256']
        assert hashlib.sha256(raw).hexdigest()==pin['sha256'] and len(raw)==pin['bytes']
        current=ROOT/path
        assert current.is_file() and not current.is_symlink()
        if path=='execution/tablet_event_summary_v890.py' and current.read_bytes()!=raw:
            assert current.read_bytes()==git('show','HEAD:'+path)
            from execution.events_collection_successor_20261123 import validate_events_collection_successor
            assert validate_events_collection_successor(path,pin['sha256'])
        elif path=='execution/tablet_menu_shell_v903.py' and current.read_bytes()!=raw:
            from execution.event_ui_successor_20261122 import validate_event_ui_successor
            assert validate_event_ui_successor(path,prior_digest=pin['sha256'])
        elif path=='execution/tablet_menu_shell_v903.js' and current.read_bytes()!=raw:
            # Preserve all historical pins and the other four live siblings.
            # Only this exact menu descendant may use its independent proof.
            from execution.menu_resize_successor_20261122 import validate_menu_resize_successor_20261122
            assert validate_menu_resize_successor_20261122(path, prior_digest=pin['sha256'])
        else:
            assert current.read_bytes()==raw==git('show','HEAD:'+path)
    for path in ('main','.github/tablet-autonomy/workspace_restore_v1017.json','.github/tablet-autonomy/deployment_repairs_successor_v1001.json'):
        assert (ROOT/path).read_bytes()==git('show',base+':'+path)
    return True

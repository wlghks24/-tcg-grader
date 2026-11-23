"""Exact undated-event retention reentry successor; source proof, never device approval."""
from pathlib import Path
import hashlib
from execution.git_validation_cache import head_validation_request
from execution.successor_git_reads_20261122 import read as read_git
ROOT=Path(__file__).resolve().parents[1]
from execution.event_validation_reads_20261123 import live_request, read_live
EXPECTED = {'baseline_commit': '3e94184d47de05edfece1869f6e093c0bcfbbc4f',
 'candidate_commit': 'ebe077c18aee08b8466f4cd7f2b41216f3b3d813',
 'baseline': {'execution/event_retention_20261123.py': {'blob': '261c85c50e79f9a5a031294521ca8c4017be8dad',
                                                        'sha256': '2c365a4127ea6dd2ca40800605e7eeb94e4404b48863a15b4645a74fd31254c5',
                                                        'bytes': 4923}},
 'files': {'execution/event_retention_20261123.py': {'blob': 'e21e2245f40ff738e254694f80e0ff10c5ecc28c',
                                                     'sha256': '889c309d10c69a696a1a1c7f50cc751d6efedc412c4f8bd9759292bc1b43b630',
                                                     'bytes': 7790},
           'execution/tests/test_event_retention_reentry_20261123.py': {'blob': '1f0cd559d67f7d45a2d8d6b2aa9aa4261a721c7c',
                                                                        'sha256': '0828d8bb42fc60df4626d5ea672c7ac35f842f904edf689790b4dcf12f6baf38',
                                                                        'bytes': 3342},
           'integrity_manifest.json': {'blob': '694655d0d219d69fee70e32118ed0889f5a1a2d1',
                                       'sha256': '82bd28bdb8cca06b8fc8b6c2681028b410d20e9704d83309c2666155955fd047',
                                       'bytes': 316602},
           'test_grading_self_learning.py': {'blob': '7dd465ea4453f98f543a9569c40c175bfcc26d90',
                                             'sha256': '7fcebdfd006080828d3afd0b4f3105f77b9167e790499c0cc4ac7ccfd9b4b0a1',
                                             'bytes': 9356}},
 'live_paths': ['execution/event_retention_20261123.py'],
 'physical_tablet_verified': False,
 'runtime_data_modified': False}

def git(*args):return read_git(ROOT,*args)

def pinned(ref,name,pin):
    raw=git('show',ref+':'+name)
    assert git('ls-tree','-z',ref,'--',name)==('100644 blob '+pin['blob']+'\t'+name+'\0').encode()
    assert len(raw)==pin['bytes'] and hashlib.sha256(raw).hexdigest()==pin['sha256']
    return raw

@head_validation_request()
@live_request
def validate_retention_reentry_successor(name,prior_digest):
    e=EXPECTED
    assert name in e['baseline'] and prior_digest==e['baseline'][name]['sha256']
    base,candidate=e['baseline_commit'],e['candidate_commit']
    git('merge-base','--is-ancestor',base,candidate)
    git('merge-base','--is-ancestor',candidate,'HEAD')
    assert git('diff','--no-renames','--name-only','-z',base,candidate).decode().split('\0')==sorted(e['files'])+['']
    for path,pin in e['baseline'].items():pinned(base,path,pin)
    for path,pin in e['files'].items():pinned(candidate,path,pin)
    for path in e['live_paths']:
        pin=e['files'][path];reviewed=pinned(candidate,path,pin)
        assert pinned('HEAD',path,pin)==reviewed
        target=ROOT/path
        assert target.is_file() and not target.is_symlink()
        assert read_live(target)==reviewed
    assert e['physical_tablet_verified'] is False and e['runtime_data_modified'] is False
    return True

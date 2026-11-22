"""Exact event presentation successor; repository proof, never device evidence."""
import hashlib
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
EXPECTED = {'baseline_commit': '4654defca3cb79c6fe3e06eeef986f97b9ecf659',
 'candidate_commit': '025cdab05e24310258cedccd51b7b83b33872d12',
 'path': 'execution/tablet_menu_shell_v903.py',
 'baseline': {'blob': '64844e602a1a523bf370b0e3c4a176822a20d730',
              'sha256': 'e9e90eabc1f77cc065209b3d4ba9f4cfb7fd12f4b19bf5895ab0477a999e9d0c',
              'bytes': 30170},
 'files': {'execution/tablet_event_labels_20261122.py': {'blob': '6bdb5cdd3bd99db2ff4e4aa55c744157a7fe78a0',
                                                         'sha256': 'fa6cd2a90a960f828d9d4066b2b124d22798954f1b14116335292450a60daf01',
                                                         'bytes': 1800},
           'execution/tablet_menu_shell_v903.py': {'blob': '33a5d17a93bead2cde284d4cd0969a2534c39bf3',
                                                   'sha256': 'b88810a0ea0b438fdf58d6c3a205a22421be8f654c2402483e6e9cd8124472da',
                                                   'bytes': 30462},
           'execution/tests/test_tablet_event_labels_20261122.py': {'blob': '7d2a0115b5553e64e3bba5a56bd2552d6355f819',
                                                                    'sha256': 'ad527522e14b11a01d1dc14058e532e1ed71038ceb9409f75a1674f0e3467936',
                                                                    'bytes': 3409},
           'integrity_manifest.json': {'blob': '0d0ab3e5cf35ddf77b0e3b55b3ef8c28d86e0208',
                                       'sha256': '0918d488e5a8d31035ed72ecf9c869688e70a58f053fe84c3ca8fd479088f596',
                                       'bytes': 311839},
           'test_grading_self_learning.py': {'blob': 'cbb4f9b174167d0db1ffd3bf2f62c4b8bf599db5',
                                             'sha256': '80bd431526c82d5babcd3a65c0c84d173b1482813ebe321cd128990c8cd1cbde',
                                             'bytes': 7859}},
 'live_paths': ['execution/tablet_menu_shell_v903.py', 'execution/tablet_event_labels_20261122.py'],
 'physical_tablet_verified': False}


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,timeout=30)


def pinned(ref,name,pin):
    assert git('ls-tree','-z',ref,'--',name)==('100644 blob '+pin['blob']+'\t'+name+'\0').encode()
    raw=git('show',ref+':'+name)
    assert len(raw)==pin['bytes'] and hashlib.sha256(raw).hexdigest()==pin['sha256']
    return raw


def validate_event_ui_successor(name,prior_digest):
    e=EXPECTED
    assert name==e['path'] and prior_digest==e['baseline']['sha256']
    base,candidate=e['baseline_commit'],e['candidate_commit']
    git('merge-base','--is-ancestor',base,candidate)
    git('merge-base','--is-ancestor',candidate,'HEAD')
    assert git('diff','--no-renames','--name-only',base,candidate).decode().splitlines()==sorted(e['files'])
    pinned(base,name,e['baseline'])
    for path,pin in e['files'].items():pinned(candidate,path,pin)
    for path in e['live_paths']:
        pin=e['files'][path]
        reviewed=pinned(candidate,path,pin)
        target=ROOT/path
        assert target.is_file() and not target.is_symlink()
        if path==e['path'] and target.read_bytes()!=reviewed:
            assert git('show','HEAD:'+path)==target.read_bytes()
            from execution.event_filter_successor_20261122 import validate_event_filter_successor
            assert validate_event_filter_successor(path, pin['sha256'])
        else:
            assert pinned('HEAD',path,pin)==reviewed
            assert target.read_bytes()==reviewed
    assert e['physical_tablet_verified'] is False
    return True

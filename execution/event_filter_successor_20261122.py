"""Exact event filter restoration successor; repository proof, never device evidence."""
from execution.git_validation_cache import head_validation_request
from execution.successor_git_reads_20261122 import read as read_git

import hashlib
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
EXPECTED = {'baseline_commit': 'd832cb6bd4856db004f84b09444d9558f8901602',
 'candidate_commit': 'dc7d31f7357e1b85f3427f7dc21a92ccd389f39f',
 'path': 'execution/tablet_menu_shell_v903.py',
 'baseline': {'blob': '33a5d17a93bead2cde284d4cd0969a2534c39bf3',
              'sha256': 'b88810a0ea0b438fdf58d6c3a205a22421be8f654c2402483e6e9cd8124472da',
              'bytes': 30462},
 'files': {'execution/tablet_event_filters_20261122.py': {'blob': '6714e081125be07e08dea398e0fb2cedaad713b5',
                                                          'sha256': '6620931085feb7efffc31ca7c5a3530564d6ab03dd83a8f2c85fec8785b89fd1',
                                                          'bytes': 4326},
           'execution/tablet_menu_shell_v903.py': {'blob': '31abfed31468eccd315bfdcf14623667d6e1e6d4',
                                                   'sha256': 'b90f21c53a3848a7238d35c419129c1c472542f6451211d3253e8fc619fb7828',
                                                   'bytes': 30665},
           'execution/tests/test_tablet_event_filters_20261122.py': {'blob': '273c8d67bef1512a9626f8f8dd17d69b5382e468',
                                                                     'sha256': '80a71fdfa9ceeadd02c141fabca004e68d21a9675bc4693aa1ecf1f7c8d4953e',
                                                                     'bytes': 5325},
           'integrity_manifest.json': {'blob': 'b9f985bc544dc87c71f9ec80de5af11dfd127b5b',
                                       'sha256': 'aa18f89c40ca224bed47743e16b38653d6e563d77e598420e411159102170835',
                                       'bytes': 312509},
           'test_grading_self_learning.py': {'blob': '4d3df545cfa2dba6dd47dc2587acc8ce01da8767',
                                             'sha256': '491ccebd03dc0b1c7c32e791d5f4c135d76001b3e0acf93c4d28606c5f0edaf3',
                                             'bytes': 8055}},
 'live_paths': ['execution/tablet_menu_shell_v903.py',
                'execution/tablet_event_filters_20261122.py'],
 'physical_tablet_verified': False}


def git(*args):
    return read_git(ROOT,*args)


def pinned(ref,name,pin):
    assert git('ls-tree','-z',ref,'--',name)==('100644 blob '+pin['blob']+'\t'+name+'\0').encode()
    raw=git('show',ref+':'+name)
    assert len(raw)==pin['bytes'] and hashlib.sha256(raw).hexdigest()==pin['sha256']
    return raw


@head_validation_request()
def validate_event_filter_successor(name,prior_digest):
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
        assert pinned('HEAD',path,pin)==reviewed
        target=ROOT/path
        assert target.is_file() and not target.is_symlink()
        assert target.read_bytes()==reviewed
    assert e['physical_tablet_verified'] is False
    return True

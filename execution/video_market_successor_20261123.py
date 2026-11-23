"""Exact sale-evidence/dashboard-link successor; source proof, never device approval."""
from pathlib import Path
import hashlib
from execution.git_validation_cache import head_validation_request
from execution.successor_git_reads_20261122 import read as read_git
ROOT=Path(__file__).resolve().parents[1]
EXPECTED = {'baseline_commit': '144fb8e9d33cac42e752d07e3d9dcc6f867fc019',
 'candidate_commit': 'b1818b429cd5067ad6cd1fbe36651edfae280ef7',
 'baseline': {'multi_market_price_collector.py': {'blob': '1773d57f4a62353220d073f519eb9bf69d7a31ee',
                                                  'sha256': '202ed3234c359d270bff14d706e2add0eba66d42730eb844c6f585ee0ff2c742',
                                                  'bytes': 60123},
              'tablet_autonomy_dashboard_v400.js': {'blob': 'b05978540a84d48dabcfdc824f672acc2ba67ffc',
                                                    'sha256': '190bba4e710812f1b2014a3b3e96c89faf3d11e84aacc6feef018334e4c48e38',
                                                    'bytes': 83325}},
 'files': {'execution/tests/test_sale_evidence_20261123.py': {'blob': '6379428c7f87f9aaeafd183315456d54596e8de8',
                                                              'sha256': 'e63f03f258fc04ef061fc8d9a8175a1cef224b125b0ca66983faaabb116c8cb3',
                                                              'bytes': 8980},
           'execution/tests/test_tablet_menu_shell_v903.js': {'blob': '9e561bcc2a9ff12456810a13751d0bbca4729b4f',
                                                              'sha256': '3160bd55ca078d79d784f8acc456db7c476d807d419517f377d40e7b0f0bd71a',
                                                              'bytes': 48763},
           'execution/tests/test_video_review_repairs_20261122.py': {'blob': 'd24cb95e1f84d8003e1d547f7e2920368f9eb7f5',
                                                                     'sha256': '9dc7804349698c9eb0f2cc2d33ef390054a08603acdf654add070b2a076c90ed',
                                                                     'bytes': 1290},
           'integrity_manifest.json': {'blob': 'f3f9bdd9ddedbb6650b855c378d22273ed11e440',
                                       'sha256': 'f978846ab8c3a8ff6464a0da5c47699548aa026f647de625f64b5ccc07bf02ca',
                                       'bytes': 314046},
           'multi_market_price_collector.py': {'blob': '6de4171fc595e45c42dfd1e11d261eb1258c98b1',
                                               'sha256': 'dc0c157fc3408310124a486f465aea5cc6c0ab6d3247c147c5b073c2bc95be6c',
                                               'bytes': 61837},
           'tablet_autonomy_dashboard_v400.js': {'blob': '068eb20aace21b5324dff0a9bc0117bf0659a0f6',
                                                 'sha256': 'd330172107e4870880b8d77d8117ce944264a6f84baf869b339c04be501fddab',
                                                 'bytes': 83660},
           'test_grading_self_learning.py': {'blob': '35607c94aa8d741845f5f1c1c01fe427bd852058',
                                             'sha256': '7b37a5815ee79c78af0f8e55d83bd6ee53d11602f57b3e6858b0a7ab35225374',
                                             'bytes': 8554}},
 'live_paths': ['multi_market_price_collector.py', 'tablet_autonomy_dashboard_v400.js'],
 'physical_tablet_verified': False,
 'runtime_data_modified': False}

def git(*args):return read_git(ROOT,*args)

def pinned(ref,name,pin):
    raw=git('show',ref+':'+name)
    assert git('ls-tree','-z',ref,'--',name)==('100644 blob '+pin['blob']+'\t'+name+'\0').encode()
    assert len(raw)==pin['bytes'] and hashlib.sha256(raw).hexdigest()==pin['sha256']
    return raw

@head_validation_request()
def validate_video_market_followup(name,prior_digest):
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
        assert target.read_bytes()==reviewed
    assert e['physical_tablet_verified'] is False and e['runtime_data_modified'] is False
    return True

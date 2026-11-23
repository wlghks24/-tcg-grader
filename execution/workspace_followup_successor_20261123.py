"""Exact calculator/status successor; source proof, never device approval."""
from pathlib import Path
import hashlib
from execution.git_validation_cache import head_validation_request
from execution.successor_git_reads_20261122 import read as read_git
ROOT=Path(__file__).resolve().parents[1]
EXPECTED = {'baseline_commit': '9b96d702e128f65afc0b4ef80e288f2ab86a409c',
 'candidate_commit': '6ce35a47faf33286b4ef22de14e00b07da950313',
 'baseline': {'execution/tablet_menu_shell_v903.js': {'blob': '3ac2ef897c301ceeff60cce56e3ae2cc8852ccf3',
                                                      'sha256': '02014c642ac51a80be1f15bb6bcbd76ba9148932d6e0ff1a8a033f995ce7cacd',
                                                      'bytes': 24475},
              'execution/tablet_menu_shell_v903.py': {'blob': '31abfed31468eccd315bfdcf14623667d6e1e6d4',
                                                      'sha256': 'b90f21c53a3848a7238d35c419129c1c472542f6451211d3253e8fc619fb7828',
                                                      'bytes': 30665}},
 'files': {'execution/tablet_menu_shell_v903.js': {'blob': 'b741b7dcd633c8bb94e5fa7dc8e5c6c092c6123f',
                                                   'sha256': 'd612179f89f97cd92fe331ec8efd6532cb80883352a4960136adfdd43de899a1',
                                                   'bytes': 25070},
           'execution/tablet_menu_shell_v903.py': {'blob': '1aba857abe5aae220feb71627f7b9b9a8e7ad7fe',
                                                   'sha256': 'ce484eed95e9ebb0cc9c02896292248522b3d9c53b92b7fe1c315526f3192679',
                                                   'bytes': 30792},
           'execution/tablet_workspace_truth_20261123.py': {'blob': '5708d7bf64d2c82e174237ec779758a22009e971',
                                                            'sha256': '22aa112e635010c18db283e177a97cd224fc049ddeeaf4d40bcf3550750b17d6',
                                                            'bytes': 2539},
           'execution/tests/test_tablet_menu_shell_v903.js': {'blob': '8b4a375e7c8b96c21f65d3adb07f5b9c939d522d',
                                                              'sha256': 'ac3c42e2f054d579362213a385961385d310a8c04401ed7af476cf7e460d3760',
                                                              'bytes': 45012},
           'execution/tests/test_tablet_workspace_truth_20261123.py': {'blob': '1a8789a41dcf8c7eb7b3090c6bd5a72a370eddd6',
                                                                       'sha256': 'cee4ef5db8ec1a1dae5ddee28f56902c34bb30b358ced86152b7b1435d25ea1e',
                                                                       'bytes': 3363},
           'execution/tests/test_video_review_repairs_20261122.py': {'blob': 'a075fbe8ed42b25593b56f8fad1853fdb7e112b6',
                                                                     'sha256': '0d3501b3a719a0e4540cac73eec55f87a1abf93d7a7a73b33c20079713859512',
                                                                     'bytes': 1290},
           'integrity_manifest.json': {'blob': '3fad270ed6db0de69d4e13f451d9265eaba8e455',
                                       'sha256': '79ce7ea0a6efc3f156105e34aac0e97043dbb59231ea0aac5044d0c10391ace8',
                                       'bytes': 313526},
           'test_grading_self_learning.py': {'blob': 'e6dd79bea2a9e8cfb6764c57e1a5520336382fc3',
                                             'sha256': '44a56d8b73f917fef44aa157098c2c1391d9d8503ef881aa6968fe365d6bbd1b',
                                             'bytes': 8355}},
 'live_paths': ['execution/tablet_menu_shell_v903.js',
                'execution/tablet_menu_shell_v903.py',
                'execution/tablet_workspace_truth_20261123.py'],
 'physical_tablet_verified': False,
 'runtime_data_modified': False}

def git(*args):return read_git(ROOT,*args)

def pinned(ref,name,pin):
    raw=git('show',ref+':'+name)
    assert git('ls-tree','-z',ref,'--',name)==('100644 blob '+pin['blob']+'\t'+name+'\0').encode()
    assert len(raw)==pin['bytes'] and hashlib.sha256(raw).hexdigest()==pin['sha256']
    return raw

@head_validation_request()
def validate_workspace_followup(name,prior_digest):
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

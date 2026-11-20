"""Exact HOT observation descendant; historic proofs remain immutable."""
import hashlib
import json
from pathlib import Path
import subprocess
from execution.git_validation_cache import git_validation_output, git_validation_run
ROOT=Path(__file__).resolve().parents[1]
EXPECTED={'schema': 'tcg-hot-evidence/v1019', 'baseline_commit': 'cdd5c41c2c6ecd13ef497f75bfec1944a7701392', 'candidate_commit': '150bb2c5580b746c356329d2be09c1002cf20db5', 'files': {'box_knowledge_stats.js': {'before_sha256': '36a3c8f9ddda83bd75e2549b4dd930d6d407274d1d8b37a0453acf6ac641b200', 'sha256': '34e54c784ea1b94b694ddc643424b744728cd0bdd2be27865cfacc6e8e682f47', 'bytes': 32465}, 'tcg_profit_radar_v47.py': {'before_sha256': 'c02212273e0cbfdd97a279ecf6c77c974cabf992c1eb4d18a39583d09af1a13a', 'sha256': '92fe7e493c72fe9895263891ebdabacb903489f654bdc981090d6bd4e532a733', 'bytes': 20863}}, 'physical_tablet_verified': False, 'runtime_data_modified': False}
def validate_hot_evidence_v1019(name, prior_digest=None):
    assert name in EXPECTED['files']
    assert prior_digest in (None,EXPECTED['files'][name]['before_sha256'])
    p=ROOT/'.github/tablet-autonomy/hot_evidence_v1019.json'
    assert p.is_file() and not p.is_symlink()
    assert json.loads(p.read_text())==EXPECTED
    base,candidate=EXPECTED['baseline_commit'],EXPECTED['candidate_commit']
    def git(*args):
        command = ['git', *args]
        # Only literal fixed-SHA ancestry and blob checks use the bounded,
        # replacement-aware cache. Candidate-to-HEAD and current bytes
        # remain live, including after warming the immutable cache.
        if args == ('merge-base', '--is-ancestor', base, candidate):
            git_validation_run(command, cwd=ROOT, capture_output=True,
                               check=True, timeout=30)
            return b''
        if (len(args) == 2 and args[0] == 'show'
                and args[1].startswith((base + ':', candidate + ':'))):
            return git_validation_output(command, cwd=ROOT, timeout=30)
        return subprocess.check_output(command, cwd=ROOT, timeout=30)
    git('merge-base','--is-ancestor',base,candidate)
    git('merge-base','--is-ancestor',candidate,'HEAD')
    assert git('diff','--name-only',base,candidate).decode().splitlines()==sorted(EXPECTED['files'])
    for path,pin in EXPECTED['files'].items():
        before=git('show',base+':'+path);raw=git('show',candidate+':'+path)
        assert hashlib.sha256(before).hexdigest()==pin['before_sha256']
        assert hashlib.sha256(raw).hexdigest()==pin['sha256'] and len(raw)==pin['bytes']
        current=ROOT/path
        assert current.is_file() and not current.is_symlink()
        live = current.read_bytes()
        if live != raw:
            # V1019 remains exact; only V1033's reviewed descendant may
            # account for a subsequent ambiguous-game HOT source change.
            assert path == 'box_knowledge_stats.js', path
            from execution.hot_game_collision_successor_v1033 import validate_hot_game_collision_v1033
            assert validate_hot_game_collision_v1033(path, prior_digest=pin['sha256'])
        else:
            assert live == git('show','HEAD:'+path)
    for path in ('main','.github/tablet-autonomy/workspace_restore_v1017.json','.github/tablet-autonomy/workspace_review_v1018.json'):
        assert (ROOT/path).read_bytes()==git('show',base+':'+path)
    return True

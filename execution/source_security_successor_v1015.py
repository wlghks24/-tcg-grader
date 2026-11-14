"""Exact security successor; retain V1009 source history and protect live JSON."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / '.github/tablet-autonomy/source_security_successor_v1015.json'
EXPECTED = {'schema': 'tcg-source-security-successor/v1015', 'baseline_commit': '378454295a28626291087a41def60ce93d10977e', 'candidate_commit': '8af1e81421fe4bd7739749e0cddfcb680229c084', 'reviewed_files': {'execution/tablet_inplace_patch.py': {'baseline_sha256': '06c97287c20a14c9aa36348d829a747ae7469c6be8c4f1c76ebb6f2d577f7188', 'baseline_bytes': 16712, 'reviewed_sha256': '585affed66e57cc7af3454ae6aa1c368a7eb7875486a52fa3970514795ac59c0', 'reviewed_bytes': 16788}, 'wyyyes_market_source.py': {'baseline_sha256': '0bb507723fd1d11ce5a13bb0e1662561cbbc0371d1560015f05b6e1a5289dbea', 'baseline_bytes': 24828, 'reviewed_sha256': '1ca75c00a3d1166a3cd2a1a7d03891de3c0b7014d13bbce977d4931aeef767d2', 'reviewed_bytes': 25927}}, 'reviewed_changed_paths': ['execution/tablet_inplace_patch.py', 'wyyyes_market_source.py'], 'prior_proof': '.github/tablet-autonomy/wyyyes_product_local_v1009.json', 'prior_proof_sha256': '84b617ab709de2ef976690acafdf0b5a61fc42046c1aee3e9b57b9a264cff89e', 'protected_main_sha256': '20409d12bf5bf5b0caadf83a530f7d26b3520b8c330cce4ce6e1c26ef089c90e', 'physical_tablet_verified': False, 'main_merge_authorized': False, 'device_restart_authorized': False, 'model_training_authorized': False}


def checked(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True,
                          check=True, timeout=30).stdout


def validate_security_successor_v1015(prior_digest=None):
    pins = EXPECTED['reviewed_files']
    assert prior_digest in (None, pins['wyyyes_market_source.py']['baseline_sha256'])
    assert PROOF.is_file() and not PROOF.is_symlink()
    assert json.loads(PROOF.read_text(encoding='utf-8')) == EXPECTED
    base, candidate = EXPECTED['baseline_commit'], EXPECTED['candidate_commit']
    checked('merge-base', '--is-ancestor', base, candidate)
    checked('merge-base', '--is-ancestor', candidate, 'HEAD')
    assert checked('diff', '--no-renames', '--name-only', base, candidate).decode().splitlines() == sorted(pins)
    for name, pin in pins.items():
        for commit, prefix in ((base, 'baseline'), (candidate, 'reviewed')):
            data = checked('show', commit + ':' + name)
            assert len(data) == pin[prefix + '_bytes']
            assert hashlib.sha256(data).hexdigest() == pin[prefix + '_sha256']
        path = ROOT / name
        assert path.is_file() and not path.is_symlink()
        data = path.read_bytes()
        if data != checked('show', candidate + ':' + name):
            assert name == 'execution/tablet_inplace_patch.py'
            from execution.login_shell_successor_v1016 import validate_login_shell_successor_v1016
            assert validate_login_shell_successor_v1016(prior_digest=pin['reviewed_sha256'])
        assert data == checked('show', 'HEAD:' + name)
    prior_path = ROOT / EXPECTED['prior_proof']
    assert prior_path.is_file() and not prior_path.is_symlink()
    prior_raw = prior_path.read_bytes()
    assert prior_raw == checked('show', base + ':' + EXPECTED['prior_proof'])
    assert hashlib.sha256(prior_raw).hexdigest() == EXPECTED['prior_proof_sha256']
    prior = json.loads(prior_raw)
    assert prior['reviewed_sha256'] == pins['wyyyes_market_source.py']['baseline_sha256']
    old = checked('show', prior['candidate_commit'] + ':' + prior['reviewed_path'])
    assert hashlib.sha256(old).hexdigest() == prior['reviewed_sha256']
    launcher = ROOT / 'main'
    assert launcher.is_file() and not launcher.is_symlink()
    assert launcher.read_bytes() == checked('show', 'HEAD:main') == checked('show', base + ':main')
    assert hashlib.sha256(launcher.read_bytes()).hexdigest() == EXPECTED['protected_main_sha256']
    return True

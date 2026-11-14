"""Exact V1016 patch-tool successor; V1015 historical evidence stays immutable."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PROOF = ROOT / '.github/tablet-autonomy/login_shell_successor_v1016.json'
EXPECTED = {'schema': 'tcg-login-shell-successor/v1016',
 'baseline_commit': 'ee1c930b95666237cc4992c7ff724442d131cba1',
 'candidate_commit': '0a4c6b4b5c244f4556f6b16d36c5b5ffb556e8de',
 'reviewed_path': 'execution/tablet_inplace_patch.py',
 'baseline_sha256': '585affed66e57cc7af3454ae6aa1c368a7eb7875486a52fa3970514795ac59c0',
 'baseline_bytes': 16788,
 'reviewed_sha256': '21af399e4f23b90305faec5abf7f5ded2a5d4834825fd12b578809542fed4238',
 'reviewed_bytes': 17152,
 'prior_proof': '.github/tablet-autonomy/source_security_successor_v1015.json',
 'prior_proof_sha256': '2380a2814d8dc7b702bd9d661bae93e3e83656a431775fa4e69b92d388eaca61',
 'protected_main_sha256': '20409d12bf5bf5b0caadf83a530f7d26b3520b8c330cce4ce6e1c26ef089c90e',
 'physical_tablet_verified': False,
 'main_merge_authorized': False,
 'device_restart_authorized': False,
 'model_training_authorized': False}


def checked(*args):
    return subprocess.run(['git', *args], cwd=ROOT, capture_output=True,
                          check=True, timeout=30).stdout


def validate_login_shell_successor_v1016(prior_digest=None):
    assert prior_digest in (None, EXPECTED['baseline_sha256'])
    assert PROOF.is_file() and not PROOF.is_symlink()
    assert json.loads(PROOF.read_text(encoding='utf-8')) == EXPECTED
    base, candidate, name = (EXPECTED[k] for k in ('baseline_commit', 'candidate_commit', 'reviewed_path'))
    checked('merge-base', '--is-ancestor', base, candidate)
    checked('merge-base', '--is-ancestor', candidate, 'HEAD')
    assert checked('diff', '--no-renames', '--name-only', base, candidate).decode().splitlines() == [name]
    for commit, prefix in ((base, 'baseline'), (candidate, 'reviewed')):
        data = checked('show', commit + ':' + name)
        assert len(data) == EXPECTED[prefix + '_bytes']
        assert hashlib.sha256(data).hexdigest() == EXPECTED[prefix + '_sha256']
    path = ROOT / name
    assert path.is_file() and not path.is_symlink()
    assert path.read_bytes() == checked('show', candidate + ':' + name) == checked('show', 'HEAD:' + name)
    prior_path = ROOT / EXPECTED['prior_proof']
    assert prior_path.is_file() and not prior_path.is_symlink()
    raw = prior_path.read_bytes()
    assert raw == checked('show', base + ':' + EXPECTED['prior_proof'])
    assert hashlib.sha256(raw).hexdigest() == EXPECTED['prior_proof_sha256']
    assert json.loads(raw)['reviewed_files'][name]['reviewed_sha256'] == EXPECTED['baseline_sha256']
    launcher = ROOT / 'main'
    assert launcher.is_file() and not launcher.is_symlink()
    assert launcher.read_bytes() == checked('show', base + ':main') == checked('show', 'HEAD:main')
    assert hashlib.sha256(launcher.read_bytes()).hexdigest() == EXPECTED['protected_main_sha256']
    return True

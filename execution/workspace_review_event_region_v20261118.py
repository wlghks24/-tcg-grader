"""Fail-closed proof for the tablet event-country UI successor.

The v1017/v1018 historical evidence remains immutable. Only the exact
reviewed source descendant is accepted; no arbitrary changed file is allowed.
"""
import hashlib
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TARGET = 'execution/tablet_unified_ui_v890.py'
BASELINE_SHA256 = 'f8bc95f52673a9923f399dfacf6612bdcbb823f776d047aaa837b6f7e9d576f9'
REVIEWED_SHA256 = '5079b76824eb9c8da1924f5f9ea3f0d145825956e7dce928dc026f46c79ede49'
REVIEWED_BYTES = 12847
REVIEWED_COMMIT = '870ba0ef32b0cd4cbcc23839d18c0e00768e104f'


def validate_event_region_successor(name, *, prior_digest=None):
    assert name == TARGET
    assert prior_digest in (None, BASELINE_SHA256)
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT, timeout=30)
    git('merge-base', '--is-ancestor', REVIEWED_COMMIT, 'HEAD')
    reviewed = git('show', REVIEWED_COMMIT + ':' + TARGET)
    assert hashlib.sha256(reviewed).hexdigest() == REVIEWED_SHA256
    assert len(reviewed) == REVIEWED_BYTES
    previous = git('show', REVIEWED_COMMIT + '^:' + TARGET)
    assert hashlib.sha256(previous).hexdigest() == BASELINE_SHA256
    path = ROOT / TARGET
    assert path.is_file() and not path.is_symlink()
    assert path.read_bytes() == reviewed == git('show', 'HEAD:' + TARGET)
    return True

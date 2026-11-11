"""Exact single-file formatting successor; historical V997 source pins stay immutable."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from execution.csp_validation_cache import assert_csp_bytes
from execution.git_validation_cache import git_validation_output

from execution.git_validation_cache import head_validation_request, resolve_validation_head

ROOT = Path(__file__).resolve().parents[2]
PROOF = ROOT / ".github/tablet-autonomy/video_verifier_successor_v999.json"
EXPECTED = {'schema': 'tcg-video-verifier-exact-index-successor/v999', 'baseline_commit': '17341a2aa2927e4283f461378e4c46ca50e377d2', 'candidate_commit': '2d8039a46a92784ea1286ff22711836b0121746e', 'reviewed_path': 'index.html', 'baseline_sha256': '970f94e1b54e2b5bcc138e27efa2b93f2c2cc2359d9eac4a92fca70a154a26ac', 'candidate_sha256': '86f80470ab283b1b265481a64a8c14524201d4aca83411d99b6501ec3c9be1fb', 'baseline_bytes': 349741, 'candidate_bytes': 349739, 'physical_tablet_runtime_verified': False, 'deployment_allowed': False, 'model_training_authorized': False, 'csp_policy_weakening_allowed': False}


def git(*args):
    return git_validation_output(["git", *args], cwd=ROOT, timeout=30)


_ORIGINAL_GIT_READER = git
_ORIGINAL_GIT_OUTPUT = git_validation_output

@lru_cache(maxsize=4)
def history(head):
    p = EXPECTED
    for older, newer in ((p["baseline_commit"], p["candidate_commit"]), (p["candidate_commit"], head)):
        assert subprocess.run(["git", "merge-base", "--is-ancestor", older, newer], cwd=ROOT,
                              capture_output=True, timeout=30).returncode == 0
    assert git("diff", "--no-renames", "--name-only", p["baseline_commit"], p["candidate_commit"]).decode().splitlines() == ["index.html"]
    for ref, digest, size in ((p["baseline_commit"], p["baseline_sha256"], p["baseline_bytes"]),
                              (p["candidate_commit"], p["candidate_sha256"], p["candidate_bytes"])):
        data = git("show", ref + ":index.html")
        assert hashlib.sha256(data).hexdigest() == digest and len(data) == size
    return True


@head_validation_request()
def validate_v999_index(prior_digest=None):
    p = EXPECTED
    assert PROOF.is_file() and not PROOF.is_symlink()
    assert json.loads(PROOF.read_text(encoding="utf-8")) == p
    if prior_digest is not None:
        assert prior_digest == p["baseline_sha256"]
    assert history(resolve_validation_head(ROOT, lambda: git("rev-parse", "HEAD"), compatible=git is _ORIGINAL_GIT_READER and git_validation_output is _ORIGINAL_GIT_OUTPUT))
    path = ROOT / "index.html"
    assert path.is_file() and not path.is_symlink()
    data = path.read_bytes()
    if len(data) != p["candidate_bytes"] or hashlib.sha256(data).hexdigest() != p["candidate_sha256"]:
        from execution.tests.test_deployment_repairs_successor_v1001 import validate_deployment_repairs_v1001
        assert validate_deployment_repairs_v1001("index.html", prior_digest=p["candidate_sha256"])
    assert assert_csp_bytes(data)
    return True


class VerifierSuccessorV999Tests(unittest.TestCase):
    def test_exact_history_live_bytes_and_no_device_claim(self):
        self.assertTrue(validate_v999_index(EXPECTED["baseline_sha256"]))
        self.assertIs(EXPECTED["deployment_allowed"], False)
        self.assertIs(EXPECTED["physical_tablet_runtime_verified"], False)

    def test_wrong_prior_digest_is_rejected(self):
        with self.assertRaises(AssertionError):
            validate_v999_index("0" * 64)

    def test_live_tamper_is_rejected_after_history_cache(self):
        validate_v999_index()
        original = Path.read_bytes
        def changed(path):
            data = original(path)
            return data + b"unreviewed" if path == ROOT / "index.html" else data
        with patch.object(Path, "read_bytes", changed), self.assertRaises(AssertionError):
            validate_v999_index()

    def test_proof_cannot_grant_installation(self):
        original = Path.read_text
        def changed(path, *a, **kw):
            text = original(path, *a, **kw)
            return text.replace('"deployment_allowed": false', '"deployment_allowed": true') if path == PROOF else text
        with patch.object(Path, "read_text", changed), self.assertRaises(AssertionError):
            validate_v999_index()


if __name__ == "__main__":
    unittest.main()

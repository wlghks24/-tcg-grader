"""Exact video repairs, independent of historical approvals or physical installation."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import csp_hash_hardening
from execution.csp_validation_cache import assert_csp_bytes
from execution.git_validation_cache import git_validation_output
from execution.tests.test_csp_validation_cache_v1000 import CSPValidationCacheV1000Tests
from execution.tests.test_successor_validation_performance_v1000 import SuccessorValidationPerformanceV1000Tests
from execution.tests.test_deployment_repairs_successor_v1001 import (
    DeploymentRepairSuccessorV1001Tests, DeploymentDatesV1001Tests, MarketInputsV1001Tests,
)
from execution.tests.test_tablet_sync_successor_v1001 import SyncV1001Tests
from execution.tests.test_scope_validation_performance_v1002 import ScopeValidationPerformanceV1002Tests
from execution.tests.test_validation_head_request_v1002 import ValidationHeadRequestV1002Tests

from execution.git_validation_cache import head_validation_request, resolve_validation_head

ROOT = Path(__file__).resolve().parents[2]
PROOF_PATH = ROOT / ".github/tablet-autonomy/video_runtime_successor_v997.json"
EXPECTED = {'schema': 'tcg-video-runtime-exact-successor/v997', 'baseline_commit': 'ce4def1b5f57fdf8729e5e7ec0a3582f524b2a4d', 'candidate_commit': '411e410a35786a565501515886b32c66401af902', 'auxiliary_paths': ['.github/workflows/tablet-v995-v996-successor-regressions.yml'], 'reviewed_files': {'box_knowledge_stats.js': {'baseline_sha256': '8ad5941d3c95246b3c5717fe68367805a0634c05ae6546091ef78dbb83f7fa91', 'candidate_sha256': '36a3c8f9ddda83bd75e2549b4dd930d6d407274d1d8b37a0453acf6ac641b200', 'candidate_bytes': 32322, 'baseline_blob': 'b0b98e7aa6212be01b873c02313f5232afac7839', 'candidate_blob': 'c0a15c4f0bb162427894319028730398ddb4214f'}, 'index.html': {'baseline_sha256': '0428f2a6f3bab08a8a5dfbae459faf658742e3827d08be152b67b3bc867146ca', 'candidate_sha256': '970f94e1b54e2b5bcc138e27efa2b93f2c2cc2359d9eac4a92fca70a154a26ac', 'candidate_bytes': 349741, 'baseline_blob': '8efab88e944d48bbcfab14b614b26031c2acdff4', 'candidate_blob': '30c64754384d9edad212b71231c08ca7ffb80192'}, 'tablet_autonomy_dashboard_v400.js': {'baseline_sha256': '8cabc0b3cb7a87ba2ca4b970a287d8cb53273b9e02238a1cc41dfb920520f47f', 'candidate_sha256': '190bba4e710812f1b2014a3b3e96c89faf3d11e84aacc6feef018334e4c48e38', 'candidate_bytes': 83325, 'baseline_blob': '656bcff887ffb37bfa27f6b6f2cfc659e9ce6722', 'candidate_blob': 'b05978540a84d48dabcfdc824f672acc2ba67ffc'}, 'tablet_image_library_v1.js': {'baseline_sha256': '57aee28c62a7bd48d9a20d82e30941fd3ed586d9119054b4859c5e629d6ed3b0', 'candidate_sha256': '13e7b4bc3834ab9f26631af32316d2cec9724404125a38d4dbaabde33a711362', 'candidate_bytes': 63315, 'baseline_blob': '43e0f92e614cca3d5d4704b3fd47c96c780a5a0d', 'candidate_blob': 'a41e014190a54ca8c1b7e44126e73ecd5e2929dc'}}, 'physical_tablet_runtime_verified': False, 'deployment_allowed': False, 'model_training_authorized': False}


def git(*args):
    return git_validation_output(["git", *args], cwd=ROOT, timeout=30)


_ORIGINAL_GIT_READER = git

@lru_cache(maxsize=4)
def history(head):
    before, after = EXPECTED["baseline_commit"], EXPECTED["candidate_commit"]
    for older, newer in ((before, after), (after, head)):
        assert subprocess.run(["git", "merge-base", "--is-ancestor", older, newer],
                              cwd=ROOT, capture_output=True, timeout=30).returncode == 0
    names = git("diff", "--no-renames", "--name-only", before, after).decode().splitlines()
    assert sorted(names) == sorted(list(EXPECTED["reviewed_files"]) + EXPECTED["auxiliary_paths"])
    for name, row in EXPECTED["reviewed_files"].items():
        for ref, field, blob_field in ((before, "baseline_sha256", "baseline_blob"),
                                      (after, "candidate_sha256", "candidate_blob")):
            data = git("show", ref + ":" + name)
            assert hashlib.sha256(data).hexdigest() == row[field], name
            assert git("rev-parse", ref + ":" + name).decode().strip() == row[blob_field], name
        assert len(git("show", after + ":" + name)) == row["candidate_bytes"], name
    return True


@head_validation_request()
def validate_v997_runtime(name, prior_digest=None):
    assert name in EXPECTED["reviewed_files"], "unreviewed V997 path"
    assert PROOF_PATH.is_file() and not PROOF_PATH.is_symlink()
    assert json.loads(PROOF_PATH.read_text(encoding="utf-8")) == EXPECTED
    if prior_digest is not None:
        assert prior_digest == EXPECTED["reviewed_files"][name]["baseline_sha256"], name
    assert history(resolve_validation_head(ROOT, lambda: git("rev-parse", "HEAD"), compatible=git is _ORIGINAL_GIT_READER))
    # Never cache current bytes/proof, even when immutable Git history was cached.
    for path, row in EXPECTED["reviewed_files"].items():
        target = ROOT / path
        assert target.is_file() and not target.is_symlink(), path
        data = target.read_bytes()
        exact = len(data) == row["candidate_bytes"] and hashlib.sha256(data).hexdigest() == row["candidate_sha256"]
        if not exact:
            # V997's immutable candidate remains pinned above. Only the
            # independently reviewed index-only verifier successor may explain
            # later live HTML; the other three runtime paths stay exact.
            assert path == "index.html", path
            from execution.tests.test_video_verifier_successor_v999 import validate_v999_index
            assert validate_v999_index(prior_digest=row["candidate_sha256"]), path
        if path == "index.html":
            assert assert_csp_bytes(data), "V997 CSP mismatch"
    return True


class VideoRuntimeSuccessorTests(unittest.TestCase):
    def test_exact_candidate_and_baseline(self):
        for name, row in EXPECTED["reviewed_files"].items():
            self.assertTrue(validate_v997_runtime(name, row["baseline_sha256"]))
        self.assertIs(EXPECTED["deployment_allowed"], False)
        self.assertIs(EXPECTED["physical_tablet_runtime_verified"], False)

    def test_unknown_path_and_wrong_baseline_are_rejected(self):
        with self.assertRaises(AssertionError):
            validate_v997_runtime("unknown.js")
        with self.assertRaises(AssertionError):
            validate_v997_runtime("index.html", "0" * 64)

    def test_warm_history_does_not_hide_any_live_tamper(self):
        validate_v997_runtime("index.html")
        original = Path.read_bytes
        for name in EXPECTED["reviewed_files"]:
            def changed(path, target=ROOT / name):
                data = original(path)
                return data + b"unreviewed" if path == target else data
            with self.subTest(name=name), patch.object(Path, "read_bytes", changed):
                with self.assertRaises(AssertionError):
                    validate_v997_runtime(name)

    def test_forged_installation_proof_is_rejected(self):
        original = Path.read_text
        def changed(path, *args, **kwargs):
            text = original(path, *args, **kwargs)
            return text.replace('"deployment_allowed": false', '"deployment_allowed": true') if path == PROOF_PATH else text
        with patch.object(Path, "read_text", changed), self.assertRaises(AssertionError):
            validate_v997_runtime("index.html")

    def test_scope_delegates_only_exact_descendants_and_preserves_unknown_history(self):
        import sync_v376_successor_test_support as sync
        radar = "tablet_image_library_v1.js"
        source = "742751dce03c711f7a4ca7a882d2fec69fb3ac55"
        self.assertEqual([], sync.preserve_reviewed_v997_runtime_scope([radar], source))
        self.assertEqual(["unknown.js"], sync.preserve_reviewed_v997_runtime_scope([radar, "unknown.js"], source))
        self.assertEqual([radar], sync.preserve_reviewed_v997_runtime_scope([radar], source, head=EXPECTED["baseline_commit"]))
        self.assertEqual([radar], sync.preserve_reviewed_v997_runtime_scope([radar], EXPECTED["candidate_commit"]))
        # A source older than the already-reviewed movie UI must retain that earlier diff.
        self.assertEqual(["index.html"], sync.preserve_reviewed_v997_runtime_scope(["index.html"], source))

    def test_scope_never_delegates_live_tampering(self):
        import sync_v376_successor_test_support as sync
        names = sorted(EXPECTED["reviewed_files"])
        original = Path.read_bytes
        for name in names:
            def changed(path, target=ROOT / name):
                data = original(path)
                return data + b"unreviewed" if path == target else data
            with self.subTest(name=name), patch.object(Path, "read_bytes", changed):
                self.assertEqual(names, sync.preserve_reviewed_v997_runtime_scope(names, EXPECTED["baseline_commit"]))


if __name__ == "__main__":
    unittest.main()

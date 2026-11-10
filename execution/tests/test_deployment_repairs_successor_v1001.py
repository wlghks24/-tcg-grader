"""Exact source successor for FX, price evidence, KST dates and runtime packaging."""
from __future__ import annotations

from functools import lru_cache
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from execution.csp_validation_cache import assert_csp_bytes
from execution.git_validation_cache import git_validation_output, git_validation_run
from execution.tests.test_market_inputs_v1001 import MarketInputsV1001Tests
from execution.tests.test_deployment_dates_v1001 import DeploymentDatesV1001Tests

from execution.git_validation_cache import head_validation_request, resolve_validation_head

ROOT = Path(__file__).resolve().parents[2]
PROOF = ROOT / ".github/tablet-autonomy/deployment_repairs_successor_v1001.json"
EXPECTED = {'schema': 'tcg-deployment-repairs-exact-successor/v1001', 'baseline_commit': '0abf05ab6e6caf571cc2ad42b8c41507fae4214d', 'candidate_commit': 'e5875ab638db531dbc805fa2967c236840afdfe9', 'reviewed_files': {'execution/tests/test_video_ui_successor_v881.py': {'baseline_sha256': '618a23b3aceb3d47d3822102da21dc5c1c613d0269429f02bf7f6c0c60f5d572', 'baseline_bytes': 4875, 'baseline_git_blob': '031c33bd7fdf69fe2b30ff8c4c6f22dfcd88dd4d', 'candidate_sha256': 'ac0e39d86e64265274ee2a0f1f825a4ee87d30479ad849416c2b9a74f391e29e', 'candidate_bytes': 5290, 'candidate_git_blob': '65c1afc3c7ca5d355e7d4e9f00b299d95f287316'}, 'index.html': {'baseline_sha256': '86f80470ab283b1b265481a64a8c14524201d4aca83411d99b6501ec3c9be1fb', 'baseline_bytes': 349739, 'baseline_git_blob': '75d4a57649758ec227446483b951cacc0cbf655a', 'candidate_sha256': '2dfeb27532f9b8ff6c6ce1761fa523d10175c73c862c715ab51bf71b60a86aeb', 'candidate_bytes': 351104, 'candidate_git_blob': 'd81920185a57a488a658751ec07e16c673d40118'}, 'static_data_publish_gate.py': {'baseline_sha256': '02cad05a459c0fcbd1258f8ab05a4201f36ea1adbbf0eca4c9cad22241dfbd4a', 'baseline_bytes': 15965, 'baseline_git_blob': '481a98422d21504537297798ca9e5d0d637f360b', 'candidate_sha256': '2530eaabdcb2b6530ee63e155a5b95653ec37f9e6a86781b94091b6cced8f2c1', 'candidate_bytes': 16097, 'candidate_git_blob': 'e895b62f42786237759e2bb20adfd483f245064f'}, 'tablet_runtime_manifest.py': {'baseline_sha256': '5ddff4d3935f4398de2d31e303a70f4b307dc737f5e11f934c0be08f9edad0de', 'baseline_bytes': 9586, 'baseline_git_blob': 'ab7a3a02d72daa528946aabc6e346634e9bb87bb', 'candidate_sha256': '480b895518014fc6cdbd46f24d78516da56597448af8d4347592fb118cc86b3f', 'candidate_bytes': 9634, 'candidate_git_blob': '68e8a5a3ace75d7e7ba1ffc4ce3ba7fb4cf3617b'}, 'update_promo_events.py': {'baseline_sha256': '0642c7aac1682212236be618a013aa9573ee8181dca5b1f2a408dfa1b1f8c670', 'baseline_bytes': 73831, 'baseline_git_blob': '8d7df5bae80f3128dc4ff08913768ab785c80231', 'candidate_sha256': '8507270fc9c76f04dfaff26b20aca7ee0a2c05c32a86f110a33ad46f2641bc04', 'candidate_bytes': 74267, 'candidate_git_blob': 'c739d3a9644bc0adff75937e1c9b7456267b3b66'}}, 'runtime_paths': ['index.html', 'static_data_publish_gate.py', 'tablet_runtime_manifest.py', 'update_promo_events.py'], 'physical_tablet_runtime_verified': False, 'deployment_allowed': False, 'model_training_authorized': False, 'csp_policy_weakening_allowed': False}


def git(*args):
    return git_validation_output(["git", *args], cwd=ROOT, timeout=30)


_ORIGINAL_GIT_READER = git
_ORIGINAL_GIT_OUTPUT = git_validation_output

@lru_cache(maxsize=4)
def _history(head, proof_key, executors):
    p = json.loads(proof_key)
    before, after = p["baseline_commit"], p["candidate_commit"]
    for older, newer in ((before, after), (after, head)):
        assert git_validation_run(["git", "merge-base", "--is-ancestor", older, newer],
                                  cwd=ROOT, capture_output=True, timeout=30).returncode == 0
    assert git("diff", "--no-renames", "--name-only", before, after).decode().splitlines() == sorted(p["reviewed_files"])
    for name, row in p["reviewed_files"].items():
        for ref, prefix in ((before, "baseline"), (after, "candidate")):
            blob = git("show", ref + ":" + name)
            assert len(blob) == row[prefix + "_bytes"], name
            assert hashlib.sha256(blob).hexdigest() == row[prefix + "_sha256"], name
            assert git("rev-parse", ref + ":" + name).decode().strip() == row[prefix + "_git_blob"], name
        if name == "index.html":
            assert assert_csp_bytes(git("show", after + ":" + name))
    return True


@head_validation_request()
def validate_deployment_repairs_v1001(name, prior_digest=None):
    assert name in EXPECTED["reviewed_files"], "unreviewed V1001 path"
    assert PROOF.is_file() and not PROOF.is_symlink()
    assert json.loads(PROOF.read_text(encoding="utf-8")) == EXPECTED
    if prior_digest is not None:
        assert prior_digest == EXPECTED["reviewed_files"][name]["baseline_sha256"], name
    head = resolve_validation_head(ROOT, lambda: git("rev-parse", "HEAD"), compatible=git is _ORIGINAL_GIT_READER and git_validation_output is _ORIGINAL_GIT_OUTPUT)
    assert _history(head, json.dumps(EXPECTED, sort_keys=True),
                    (subprocess.run, subprocess.check_output))
    # Proofs and every reviewed live file are re-read on each call. No cached
    # historical result can turn a changed local file into reviewed source.
    for path, row in EXPECTED["reviewed_files"].items():
        target = ROOT / path
        assert target.is_file() and not target.is_symlink(), path
        blob = target.read_bytes()
        assert len(blob) == row["candidate_bytes"], path
        assert hashlib.sha256(blob).hexdigest() == row["candidate_sha256"], path
        if path == "index.html":
            assert assert_csp_bytes(blob)
    return True


class DeploymentRepairSuccessorV1001Tests(unittest.TestCase):
    def test_exact_scope_ancestry_live_bytes_and_unverified_device(self):
        for name, row in EXPECTED["reviewed_files"].items():
            self.assertTrue(validate_deployment_repairs_v1001(name, row["baseline_sha256"]))
        for key in ("physical_tablet_runtime_verified", "deployment_allowed",
                    "model_training_authorized", "csp_policy_weakening_allowed"):
            self.assertIs(EXPECTED[key], False)

    def test_unknown_path_and_wrong_prior_are_rejected(self):
        for name, digest in (("main", None), ("index.html", "0" * 64)):
            with self.subTest(name=name), self.assertRaises(AssertionError):
                validate_deployment_repairs_v1001(name, digest)

    def test_live_tamper_is_rejected_after_history_cache(self):
        validate_deployment_repairs_v1001("index.html")
        original = Path.read_bytes
        for name in EXPECTED["reviewed_files"]:
            def changed(path, target=ROOT / name):
                data = original(path)
                return data + b"unreviewed" if path == target else data
            with self.subTest(name=name), patch.object(Path, "read_bytes", changed), self.assertRaises(AssertionError):
                validate_deployment_repairs_v1001(name)

    def test_proof_tamper_cannot_grant_deployment(self):
        original = Path.read_text
        def changed(path, *a, **kw):
            data = original(path, *a, **kw)
            return data.replace('"deployment_allowed": false', '"deployment_allowed": true') if path == PROOF else data
        with patch.object(Path, "read_text", changed), self.assertRaises(AssertionError):
            validate_deployment_repairs_v1001("index.html")

    def test_scope_preserves_unknown_and_earlier_edits(self):
        import sync_v376_successor_test_support as sync
        base = EXPECTED["baseline_commit"]
        self.assertEqual(["unknown.js"], sync.preserve_reviewed_v1001_scope(
            ["index.html", "unknown.js"], base))
        self.assertEqual(["index.html"], sync.preserve_reviewed_v1001_scope(
            ["index.html"], "742751dce03c711f7a4ca7a882d2fec69fb3ac55"))


if __name__ == "__main__":
    unittest.main()

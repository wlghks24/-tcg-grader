"""V998 exact workflow scope; historical V641 records remain unchanged."""
from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from functools import lru_cache
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PROOF_PATH = ROOT / ".github/tablet-autonomy/runtime_scope_successor_v998.json"
EXPECTED = json.loads(r'''{"schema":"tcg-v998-exact-runtime-scope-successor/1","candidate_commit":"411e410a35786a565501515886b32c66401af902","reviewed_files":{".github/workflows/tablet-autonomy-patch-checks.yml":{"baseline_commit":"dcf287caf103d0aa19c5aec0231e5643096eee67","last_change_commit":"0860217da68683428e6e80cbe7a2fdf2b20040d7","baseline_git_blob":"8ee5392604a60d7060ac98eb819eff717fd2f07a","baseline_sha256":"831e5a2b030c15fb43c7c450de7ba815f5f59827f1fa9e07670af6959dd40ac6","baseline_bytes":1479,"candidate_git_blob":"8ee5392604a60d7060ac98eb819eff717fd2f07a","candidate_sha256":"831e5a2b030c15fb43c7c450de7ba815f5f59827f1fa9e07670af6959dd40ac6","candidate_bytes":1479},".github/workflows/tablet-v995-v996-successor-regressions.yml":{"baseline_commit":"2e98c3f1791fea21fc7d94c7122caee7a2c9f6da","last_change_commit":"411e410a35786a565501515886b32c66401af902","baseline_git_blob":null,"baseline_sha256":null,"baseline_bytes":null,"candidate_git_blob":"5cb0d446191b25b1990de2be4f8d4c7af9b01ca4","candidate_sha256":"6e62cd98d6c8dfe90973729efebe6b58c1abf91939499a0098d522437d6990b5","candidate_bytes":2414},"tablet_autonomous_evolution_v372.py":{"baseline_commit":"dcf287caf103d0aa19c5aec0231e5643096eee67","last_change_commit":"3e021bbcf79518b927f54875eff8d56cb6c8a9bc","baseline_git_blob":"3ae652d13903194f96ada38c8308e586b71cb3c7","baseline_sha256":"0cab6ba76f339f33800d2210fd9e3cd7b332f54dd5f505eb692e949e505e6170","baseline_bytes":28440,"candidate_git_blob":"3ae652d13903194f96ada38c8308e586b71cb3c7","candidate_sha256":"0cab6ba76f339f33800d2210fd9e3cd7b332f54dd5f505eb692e949e505e6170","candidate_bytes":28440},"tablet_autonomous_evolution_v387.py":{"baseline_commit":"dcf287caf103d0aa19c5aec0231e5643096eee67","last_change_commit":"38ee3f930752b8031a7b0c5474b3e23f494b1b45","baseline_git_blob":"d102438260fcc7121ae93720392ba3eb756929d5","baseline_sha256":"006f62226eeb26abd9f0a13661d066c497381c37d0ce699b0b5f167e345ad4ae","baseline_bytes":31069,"candidate_git_blob":"d102438260fcc7121ae93720392ba3eb756929d5","candidate_sha256":"006f62226eeb26abd9f0a13661d066c497381c37d0ce699b0b5f167e345ad4ae","candidate_bytes":31069}},"historical_v641_immutable":true,"deployment_allowed":false,"physical_tablet_runtime_verified":false,"model_training_authorized":false}''')
NEW_WORKFLOW = ".github/workflows/tablet-v995-v996-successor-regressions.yml"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, timeout=30)


def ancestor(a, b):
    return subprocess.run(["git", "merge-base", "--is-ancestor", a, b],
                          cwd=ROOT, capture_output=True, timeout=30).returncode == 0


@lru_cache(maxsize=4)
def _historical_evidence(head_sha):
    candidate = EXPECTED["candidate_commit"]
    assert ancestor(candidate, head_sha), "V998 missing candidate ancestry"
    for name, row in EXPECTED["reviewed_files"].items():
        base, changed = row["baseline_commit"], row["last_change_commit"]
        assert ancestor(base, candidate), name
        assert ancestor(changed, candidate), name
        assert git("log", "-1", "--format=%H", candidate, "--", name).decode().strip() == changed
        for revision, step in ((base, "baseline"), (candidate, "candidate")):
            if row[step + "_git_blob"] is None:
                absent = subprocess.run(["git", "cat-file", "-e", revision + ":" + name],
                                        cwd=ROOT, capture_output=True, timeout=30)
                assert absent.returncode != 0, (name, "expected absent baseline")
                continue
            blob = git("show", revision + ":" + name)
            assert hashlib.sha256(blob).hexdigest() == row[step + "_sha256"], name
            assert len(blob) == row[step + "_bytes"], name
            assert git("rev-parse", revision + ":" + name).decode().strip() == row[step + "_git_blob"], name
    return True


def validate_runtime_scope_v998():
    """Re-read live files/proof on every call; only immutable history is cached."""
    assert PROOF_PATH.is_file() and not PROOF_PATH.is_symlink(), "V998 missing/linked proof"
    assert json.loads(PROOF_PATH.read_text(encoding="utf-8")) == EXPECTED, "V998 proof mismatch"
    assert _historical_evidence(git("rev-parse", "HEAD").decode().strip())
    for name, row in EXPECTED["reviewed_files"].items():
        target = ROOT / name
        assert target.is_file() and not target.is_symlink(), name
        live = target.read_bytes()
        assert hashlib.sha256(live).hexdigest() == row["candidate_sha256"], name
        assert len(live) == row["candidate_bytes"], name
    return sorted(EXPECTED["reviewed_files"])


class RuntimeScopeSuccessorV998Tests(unittest.TestCase):
    def test_exact_four_pins_and_v641_history(self):
        import sync_v376_successor_test_support as sync
        self.assertEqual(sorted(EXPECTED["reviewed_files"]), validate_runtime_scope_v998())
        self.assertIs(EXPECTED["deployment_allowed"], False)
        self.assertIs(EXPECTED["physical_tablet_runtime_verified"], False)
        for name in sync.V641_GAPS:
            self.assertEqual(sync.V641_PINS[name], EXPECTED["reviewed_files"][name]["baseline_sha256"])

    def test_only_new_workflow_is_delegated_and_unknown_paths_survive(self):
        import sync_v376_successor_test_support as sync
        source = EXPECTED["reviewed_files"][NEW_WORKFLOW]["baseline_commit"]
        visible = [NEW_WORKFLOW, "unknown.py", "tablet_autonomous_evolution_v372.py"]
        self.assertEqual(visible[1:], sync.preserve_reviewed_v998_runtime_scope(visible, source))
        self.assertEqual(visible, sync.preserve_reviewed_v998_runtime_scope(visible, source, head=source))

    def test_changed_prebaseline_workflow_is_not_hidden(self):
        import sync_v376_successor_test_support as sync
        # Once a source already contains this workflow, a later difference is
        # not evidence of the original new-file scope and must stay visible.
        self.assertEqual([NEW_WORKFLOW], sync.preserve_reviewed_v998_runtime_scope(
            [NEW_WORKFLOW], EXPECTED["candidate_commit"]))

    def test_prebaseline_difference_is_retained_even_with_exact_candidate(self):
        import sync_v376_successor_test_support as sync
        source = EXPECTED["reviewed_files"][NEW_WORKFLOW]["baseline_commit"]
        original = subprocess.check_output
        def changed_scope(args, *a, **kw):
            if args[:4] == ["git", "diff", "--no-renames", "--name-only"]:
                return NEW_WORKFLOW + "\n"
            return original(args, *a, **kw)
        with patch.object(subprocess, "check_output", changed_scope):
            self.assertEqual([NEW_WORKFLOW], sync.preserve_reviewed_v998_runtime_scope([NEW_WORKFLOW], source))

    def test_proof_tamper_retains_watched_scope(self):
        import sync_v376_successor_test_support as sync
        original = Path.read_text
        source = EXPECTED["reviewed_files"][NEW_WORKFLOW]["baseline_commit"]
        def changed(path, *a, **kw):
            blob = original(path, *a, **kw)
            return blob.replace('"historical_v641_immutable": true',
                                '"historical_v641_immutable": false') if path == PROOF_PATH else blob
        with patch.object(Path, "read_text", changed):
            self.assertEqual([NEW_WORKFLOW], sync.preserve_reviewed_v998_runtime_scope([NEW_WORKFLOW], source))

    def test_every_live_file_tamper_rejected_even_after_warmup(self):
        validate_runtime_scope_v998()
        original = Path.read_bytes
        for name in EXPECTED["reviewed_files"]:
            target = ROOT / name
            def altered(path, target=target):
                blob = original(path)
                return blob + b"\n# unreviewed" if path == target else blob
            with self.subTest(name=name), patch.object(Path, "read_bytes", altered):
                with self.assertRaises(AssertionError):
                    validate_runtime_scope_v998()
                import sync_v376_successor_test_support as sync
                base = EXPECTED["reviewed_files"][NEW_WORKFLOW]["baseline_commit"]
                self.assertEqual([NEW_WORKFLOW], sync.preserve_reviewed_v998_runtime_scope([NEW_WORKFLOW], base))

    def test_proof_flags_cannot_grant_release(self):
        original = Path.read_text
        def altered(path, *args, **kwargs):
            blob = original(path, *args, **kwargs)
            return blob.replace('"deployment_allowed": false', '"deployment_allowed": true') if path == PROOF_PATH else blob
        with patch.object(Path, "read_text", altered), self.assertRaises(AssertionError):
            validate_runtime_scope_v998()

    def test_missing_history_rejects_candidate(self):
        with patch(__name__ + ".ancestor", return_value=False), self.assertRaises(AssertionError):
            _historical_evidence.__wrapped__("0" * 40)


if __name__ == "__main__":
    unittest.main()

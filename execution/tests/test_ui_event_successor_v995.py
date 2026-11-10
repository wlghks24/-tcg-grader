"""V995 exact, fail-closed successor for the later reviewed movie UI and event code."""
from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from functools import lru_cache
from pathlib import Path
from unittest.mock import patch

import csp_hash_hardening
from execution.git_validation_cache import git_validation_output, git_validation_run

ROOT = Path(__file__).resolve().parents[2]
PROOF_PATH = ROOT / ".github/tablet-autonomy/ui_event_successor_v995.json"
EXPECTED = json.loads(r'''{"schema":"tcg-v995-ui-event-exact-descendants/1","reviewed_files":{"index.html":{"baseline_commit":"742751dce03c711f7a4ca7a882d2fec69fb3ac55","baseline_git_blob":"5903812cb04f17aa682550f2bbea5881abd813a4","candidate_commit":"acf08fc05f3b16ea388c863bbffdec173e7dcf99","candidate_git_blob":"8efab88e944d48bbcfab14b614b26031c2acdff4","candidate_sha256":"0428f2a6f3bab08a8a5dfbae459faf658742e3827d08be152b67b3bc867146ca","candidate_bytes":348532},"update_promo_events.py":{"baseline_commit":"25541824d810f5c99563faa8edc53a10b25bb32a","baseline_git_blob":"1bd5b4021c38f56e881cb793c9ac19efe127180a","candidate_commit":"21103500b6c7879027a4067f5ac68ae7cb9d17fc","candidate_git_blob":"8d7df5bae80f3128dc4ff08913768ab785c80231","candidate_sha256":"0642c7aac1682212236be618a013aa9573ee8181dca5b1f2a408dfa1b1f8c670","candidate_bytes":73831}},"prior_v881_v882_evidence_immutable":true,"physical_tablet_runtime_verified":false,"deployment_allowed":false,"model_training_authorized":false,"csp_policy_weakening_allowed":false}''')


def git(*args, data=None):
    options = {"cwd": ROOT, "timeout": 30}
    if data is not None:
        options["input"] = data
    return git_validation_output(["git", *args], **options)


def ancestor(older, newer):
    return git_validation_run(
        ["git", "merge-base", "--is-ancestor", older, newer],
        cwd=ROOT, capture_output=True, timeout=30
    ).returncode == 0


@lru_cache(maxsize=4)
def _historical_candidate_evidence(head_sha):
    """Cache only immutable Git objects; never cache live proof/file readings."""
    for name, row in EXPECTED["reviewed_files"].items():
        assert ancestor(row["baseline_commit"], row["candidate_commit"]), name
        assert ancestor(row["candidate_commit"], head_sha), name
        changed = git(
            "diff", "--no-renames", "--name-only",
            row["baseline_commit"], row["candidate_commit"], "--", name
        ).decode("utf-8", "strict").splitlines()
        assert changed == [name], ("unexpected successor scope", name, changed)
        baseline = git("show", row["baseline_commit"] + ":" + name)
        candidate = git("show", row["candidate_commit"] + ":" + name)
        assert git("hash-object", "--stdin", data=baseline).decode().strip() == row["baseline_git_blob"]
        assert git("hash-object", "--stdin", data=candidate).decode().strip() == row["candidate_git_blob"]
        assert hashlib.sha256(candidate).hexdigest() == row["candidate_sha256"]
        assert len(candidate) == row["candidate_bytes"]
        if name == "index.html":
            html = candidate.decode("utf-8", "strict")
            assert csp_hash_hardening.harden_html(html) == html, "V995 inline CSP stale"
    return True


def validate_v995_successors():
    """Every call checks current proof and current bytes, even after cached history."""
    assert PROOF_PATH.is_file() and not PROOF_PATH.is_symlink()
    assert json.loads(PROOF_PATH.read_text(encoding="utf-8")) == EXPECTED
    head = git("rev-parse", "HEAD").decode("ascii").strip()
    assert _historical_candidate_evidence(head)
    for name, row in EXPECTED["reviewed_files"].items():
        path = ROOT / name
        assert path.is_file() and not path.is_symlink(), name
        live = path.read_bytes()
        if len(live) != row["candidate_bytes"] or hashlib.sha256(live).hexdigest() != row["candidate_sha256"]:
            assert name == "index.html", name
            from execution.tests.test_video_runtime_successor_v997 import validate_v997_runtime
            assert validate_v997_runtime(name, prior_digest=row["candidate_sha256"]), name
    return sorted(EXPECTED["reviewed_files"])


class UIEventSuccessorV995Tests(unittest.TestCase):
    def test_current_exact_pins_and_old_evidence_unchanged(self):
        self.assertEqual(["index.html", "update_promo_events.py"], validate_v995_successors())
        self.assertIs(EXPECTED["deployment_allowed"], False)
        self.assertIs(EXPECTED["physical_tablet_runtime_verified"], False)
        old = git("show", "742751dce03c711f7a4ca7a882d2fec69fb3ac55:index.html")
        self.assertEqual("5571f458de1375f3cbf410a13bdbd54308e180d00df8d2f00e654af0e23d4647",
                         hashlib.sha256(old).hexdigest())

    def test_every_live_file_tamper_fails_closed_even_after_cache(self):
        validate_v995_successors()
        original = Path.read_bytes
        for name in EXPECTED["reviewed_files"]:
            target = ROOT / name
            def fake_read(path, target=target):
                blob = original(path)
                return blob + b"\n#unreviewed" if path == target else blob
            with self.subTest(name=name), patch.object(Path, "read_bytes", fake_read):
                with self.assertRaises(AssertionError):
                    validate_v995_successors()

    def test_proof_tamper_disallows_delegation(self):
        import sync_v376_successor_test_support as sync
        watched = sorted(EXPECTED["reviewed_files"])
        source = "742751dce03c711f7a4ca7a882d2fec69fb3ac55"
        self.assertEqual([], sync.preserve_reviewed_v995_ui_event_scope(watched, source))
        original = Path.read_text
        def fake_text(path, *a, **kw):
            blob = original(path, *a, **kw)
            if path == PROOF_PATH:
                return blob.replace('"deployment_allowed": false', '"deployment_allowed": true')
            return blob
        with patch.object(Path, "read_text", fake_text):
            self.assertEqual(watched, sync.preserve_reviewed_v995_ui_event_scope(watched, source))

    def test_v653_workspace_event_history_and_exact_descendant(self):
        """A V653 historical hash is not rewritten to match latest movie data."""
        import sync_v376_successor_test_support as sync
        name = "update_promo_events.py"
        row = EXPECTED["reviewed_files"][name]
        self.assertEqual(sync.V653_PROOF["candidate_commit"], row["baseline_commit"])
        self.assertEqual(sync.V653_PROOF["reviewed_sha256"][name],
                         hashlib.sha256(git("show", row["baseline_commit"] + ":" + name)).hexdigest())
        self.assertIn(name, validate_v995_successors())
        # Exercise the real immutable V653 validator and its V995 delegation.
        sync.assert_v653_successor(self)

    def test_v884_historical_ui_pin_and_v995_exact_live_successor(self):
        import sync_v376_successor_test_support as sync
        c = sync.assert_v884_successor(self)
        self.assertEqual(
            "5571f458de1375f3cbf410a13bdbd54308e180d00df8d2f00e654af0e23d4647",
            c["candidate_sync"]["reviewed_sha256"]["index.html"])
        self.assertNotEqual(
            c["candidate_sync"]["reviewed_sha256"]["index.html"],
            sync.V995_POST_V884_PROOF["reviewed_sha256"]["index.html"])
        self.assertEqual(
            ["index.html", "update_promo_events.py"], sync.verify_v995_post_v884())

    def test_v884_exact_successor_still_rejects_new_live_ui_tampering(self):
        import sync_v376_successor_test_support as sync
        sync.assert_v884_successor(self)
        original = Path.read_bytes
        target = ROOT / "index.html"
        def modified(path):
            blob = original(path)
            return blob + b"\\n<!-- unreviewed -->" if path == target else blob
        with patch.object(Path, "read_bytes", modified):
            with self.assertRaises(AssertionError):
                sync.assert_v884_successor(self)

    def test_legacy_v884_and_v657_still_verify_reviewed_descendants(self):
        import sync_v376_successor_test_support as sync
        self.assertTrue(sync.assert_v884_successor(self))
        source = sync.V657_PROOF["candidate_commit"]
        self.assertEqual([], sync.preserve_reviewed_v657_scope(
            ["update_promo_events.py"], source))
        self.assertEqual([], sync.preserve_reviewed_v881_scope(
            ["update_promo_events.py"], sync.V880_PROOF["candidate_commit"]))

    def test_legacy_promo_scopes_reject_unreviewed_current_bytes(self):
        import sync_v376_successor_test_support as sync
        original = Path.read_bytes
        target = ROOT / "update_promo_events.py"
        def tampered(path):
            data = original(path)
            return data + b"\\n# unreviewed" if path == target else data
        with patch.object(Path, "read_bytes", tampered):
            self.assertEqual(["update_promo_events.py"],
                sync.preserve_reviewed_v657_scope(
                    ["update_promo_events.py"], sync.V657_PROOF["candidate_commit"]))
            self.assertEqual(["update_promo_events.py"],
                sync.preserve_reviewed_v881_scope(
                    ["update_promo_events.py"], sync.V880_PROOF["candidate_commit"]))

    def test_historical_prebaseline_index_stays_visible(self):
        import sync_v376_successor_test_support as sync
        previous = "f538d136c033f838016e910cd24374a79dbc0b15"
        self.assertEqual(["index.html"], sync.preserve_reviewed_v995_ui_event_scope(
            ["index.html"], previous))
        self.assertEqual(["index.html"], sync.preserve_reviewed_v995_ui_event_scope(
            ["index.html"], "742751dce03c711f7a4ca7a882d2fec69fb3ac55",
            head="acf08fc05f3b16ea388c863bbffdec173e7dcf99"))


if __name__ == "__main__":
    unittest.main()

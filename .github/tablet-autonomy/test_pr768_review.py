"""Fail-closed integrity checks for PR #768's evidence inventory."""
import json
import subprocess
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVIEW = Path(__file__).resolve().parent / "pr768_review.json"

# Independent reviewed byte pins: changing the JSON and code together must fail.
PINNED_REVIEWED_BLOBS = {
    "TABLET_SCHEDULED_UPDATE.sh": "aacf20bc8d41a40afecacf01d82edcf1221fb4f2",
    "tablet_autonomous_evolution_v372.py": "3ae652d13903194f96ada38c8308e586b71cb3c7",
    "tablet_autonomous_evolution_v387.py": "d102438260fcc7121ae93720392ba3eb756929d5",
    ".github/workflows/tablet-autonomy-patch-checks.yml": "8ee5392604a60d7060ac98eb819eff717fd2f07a",
}
PINNED_CANDIDATE = "f11fd075a6f583a8fb601de1d8204e722e38b360"


class TabletAutonomyReviewTests(unittest.TestCase):
    def test_review_is_non_deployable_until_sync_and_device_proof(self):
        data = json.loads(REVIEW.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"], "tablet-autonomy-review/v1")
        self.assertIs(data["deployment_allowed"], False)
        self.assertEqual(data["pr"], 768)
        self.assertEqual(len(data["candidate_commit"]), 40)
        self.assertNotEqual(data["candidate_commit"], "0" * 40)
        self.assertTrue(all(c in "0123456789abcdef" for c in data["candidate_commit"]))
        self.assertEqual(data["candidate_commit"], PINNED_CANDIDATE)
        self.assertEqual(data["status"], "PENDING_SYNC_SUCCESSOR_AND_DEVICE_VALIDATION")
        self.assertIn("Exhaustive SELFREFINE Guard", data["blocked_checks"])
        self.assertIn("Tablet GPT TCG Grader Main Alignment", data["blocked_checks"])
        self.assertIn("Tablet Autonomy Patch Checks", data["verified_checks"])
        self.assertNotIn("Tablet GPT TCG Grader Main Alignment", data["verified_checks"])
        self.assertTrue(data["blocked_checks"])
        self.assertEqual(len(data["blocked_checks"]), len(set(data["blocked_checks"])))
        self.assertEqual(len(data["verified_checks"]), len(set(data["verified_checks"])))
        self.assertTrue(set(data["blocked_checks"]).isdisjoint(data["verified_checks"]))
        self.assertIn("deployment", data["notes"].lower())

    def test_v426_watched_changes_are_not_silently_approved(self):
        """Keep the three known V426 gaps visible until a reviewed successor exists."""
        import sys
        sys.path.insert(0, str(ROOT))
        import sync_v376_successor_test_support as sync
        contract = json.loads(sync.V426_CONTRACT_PATH.read_text(encoding="utf-8"))
        ancestor = subprocess.run(
            ["git", "cat-file", "-e", f"{sync.V426_CANDIDATE}^{{commit}}"],
            cwd=ROOT, capture_output=True, check=False,
        )
        self.assertEqual(
            ancestor.returncode, 0,
            "V426 historical commit is required for the full-history PR768 gate; "
            "fetch history rather than skipping the comparison",
        )
        visible = set(sync._watched_paths(contract, sync.V426_CANDIDATE))
        approved = set(sync.V427_WATCHED + sync.V431_WATCHED + sync.V432_WATCHED +
                       sync.V439_WATCHED + sync.V440_WATCHED + sync.V469_WATCHED +
                       sync.V470_WATCHED + sync.V471_WATCHED + sync.V480_WATCHED)
        unresolved = visible - approved
        self.assertEqual(unresolved, {
            ".github/workflows/tablet-autonomy-patch-checks.yml",
            "tablet_autonomous_evolution_v372.py",
            "tablet_autonomous_evolution_v387.py",
        })

    def test_reviewed_candidate_is_ancestor_of_current_head(self):
        """Evidence must refer to a real integrated commit, not an arbitrary SHA."""
        data = json.loads(REVIEW.read_text(encoding="utf-8"))
        candidate = data["candidate_commit"]
        present = subprocess.run(
            ["git", "cat-file", "-e", f"{candidate}^{{commit}}"],
            cwd=ROOT, capture_output=True, check=False,
        )
        self.assertEqual(present.returncode, 0, "reviewed candidate commit is missing")
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", candidate, "HEAD"],
            cwd=ROOT, capture_output=True, check=False,
        )
        self.assertEqual(ancestor.returncode, 0,
                         "reviewed candidate must be an ancestor of HEAD")

    def test_sync_successor_has_exact_pinned_scope(self):
        """Prove the three new watched files are the only PR768 successor scope."""
        import sys
        sys.path.insert(0, str(ROOT))
        import sync_v376_successor_test_support as sync
        review = json.loads(REVIEW.read_text(encoding="utf-8"))
        candidate = review["candidate_commit"]
        contract = json.loads(sync.V426_CONTRACT_PATH.read_text(encoding="utf-8"))
        approved = set(sync.V427_WATCHED + sync.V431_WATCHED + sync.V432_WATCHED +
                       sync.V439_WATCHED + sync.V440_WATCHED + sync.V469_WATCHED +
                       sync.V470_WATCHED + sync.V471_WATCHED + sync.V480_WATCHED)
        scope = set(sync._watched_paths(contract, sync.V426_CANDIDATE)) - approved
        expected = {
            ".github/workflows/tablet-autonomy-patch-checks.yml",
            "tablet_autonomous_evolution_v372.py",
            "tablet_autonomous_evolution_v387.py",
        }
        self.assertEqual(scope, expected, "unreviewed watched paths must block")
        reviewed = {item["path"]: item["git_blob_sha"]
                    for item in review["reviewed_files"]}
        self.assertTrue(scope.issubset(reviewed))
        self.assertEqual(reviewed, PINNED_REVIEWED_BLOBS)
        for path in sorted(scope):
            with self.subTest(path=path):
                current = subprocess.check_output(
                    ["git", "hash-object", "--", path], cwd=ROOT, text=True
                ).strip()
                self.assertEqual(current, reviewed[path],
                                 "successor scope has unreviewed bytes")
                # Compare the historical generation directly with the claimed
                # candidate. Any prior edit must remain visible to the sync
                # successor reviewer; never infer a clean boundary from HEAD.
                prior = subprocess.run(
                    ["git", "diff", "--name-only",
                     f"{sync.V426_CANDIDATE}..{candidate}", "--", path],
                    cwd=ROOT, capture_output=True, text=True, check=False,
                )
                self.assertEqual(prior.returncode, 0,
                                 "cannot establish historical review boundary")
                self.assertIn(
                    path, prior.stdout.splitlines(),
                    "candidate does not account for the historical watched change",
                )
                # This test audits the candidate and pinned bytes; it does not
                # waive the historical sync guard or authorize deployment.

    def test_reviewed_blobs_are_exact_and_unchanged(self):
        data = json.loads(REVIEW.read_text(encoding="utf-8"))
        files = data["reviewed_files"]
        self.assertEqual(len(files), 4)
        paths = [item["path"] for item in files]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(set(paths), set(PINNED_REVIEWED_BLOBS))
        self.assertEqual(data["candidate_commit"], PINNED_CANDIDATE)
        for item in files:
            with self.subTest(path=item["path"]):
                self.assertEqual(len(item["git_blob_sha"]), 40)
                self.assertNotEqual(item["git_blob_sha"], "0" * 40)
                self.assertTrue(all(c in "0123456789abcdef" for c in item["git_blob_sha"]))
                path = ROOT / item["path"]
                self.assertTrue(path.resolve().is_relative_to(ROOT.resolve()))
                self.assertFalse(path.is_symlink())
                self.assertTrue(path.is_file())
                actual = subprocess.check_output(
                    ["git", "hash-object", "--", str(path)], cwd=ROOT, text=True
                ).strip()
                self.assertEqual(item["git_blob_sha"], PINNED_REVIEWED_BLOBS[item["path"]])
                self.assertEqual(actual, PINNED_REVIEWED_BLOBS[item["path"]])


class TabletAutonomySuccessorV641Tests(unittest.TestCase):
    def test_exact_review_satisfies_only_known_historical_gaps(self):
        import sync_v376_successor_test_support as sync
        sync.assert_v641_autonomy_successor(self)
        for generation in ("V426", "V427", "V428", "V431", "V432"):
            sync._assert_successor_paths_reviewed(
                self, sorted(sync.V641_GAPS), [], generation=generation)

    def test_unrelated_path_or_generation_remains_blocked(self):
        import sync_v376_successor_test_support as sync
        with self.assertRaises(AssertionError):
            sync._assert_successor_paths_reviewed(
                self, ["main"], [], generation="V426")
        with self.assertRaises(AssertionError):
            sync._assert_successor_paths_reviewed(
                self, sorted(sync.V641_GAPS), [], generation="V425")

    def test_modified_runtime_bytes_remain_blocked(self):
        mock = unittest.mock
        import sync_v376_successor_test_support as sync
        original = Path.read_bytes
        def changed(path):
            if path == ROOT / "tablet_autonomous_evolution_v372.py":
                return original(path) + b"\n# unreviewed edit\n"
            return original(path)
        with mock.patch.object(Path, "read_bytes", changed):
            with self.assertRaises(AssertionError):
                sync.assert_v641_autonomy_successor(self)

    def test_forged_proof_cannot_grant_deployment(self):
        mock = unittest.mock
        import sync_v376_successor_test_support as sync
        original = sync._read
        def forged(path):
            data = original(path)
            if path.name == "sync_successor_v641.json":
                data["deployment_allowed"] = True
            return data
        with mock.patch.object(sync, "_read", forged):
            with self.assertRaises(AssertionError):
                sync.assert_v641_autonomy_successor(self)

    def test_legacy_delegation_retains_prior_changes_and_unknown_sources(self):
        import sync_v376_successor_test_support as sync
        source = sync.V381_CANDIDATE
        paths = sorted(sync.V641_GAPS)
        prior = subprocess.check_output(
            ["git", "diff", "--name-only", f"{source}..{sync.V641_BASE}", "--", *paths],
            cwd=ROOT, text=True).splitlines()
        self.assertEqual(sorted(set(paths) & set(prior)),
                         sync.preserve_reviewed_v641_autonomy_scope(paths, source))
        self.assertEqual(paths,
            sync.preserve_reviewed_v641_autonomy_scope(paths, sync.V426_CANDIDATE))
        self.assertEqual(paths,
            sync.preserve_reviewed_v641_autonomy_scope(paths, source, sync.V641_BASE))

    def test_legacy_delegation_fails_closed_when_proof_is_invalid(self):
        mock = unittest.mock
        import sync_v376_successor_test_support as sync
        paths = sorted(sync.V641_GAPS)
        with mock.patch.object(sync, "assert_v641_autonomy_successor",
                               side_effect=AssertionError("unreviewed bytes")):
            self.assertEqual(paths,
                sync.preserve_reviewed_v641_autonomy_scope(paths, sync.V381_CANDIDATE))


class TabletUiDomSuccessorV642Tests(unittest.TestCase):
    def test_exact_review_only_delegates_new_checker_bytes(self):
        import sync_v376_successor_test_support as sync
        path = sync.V642_UI_PROOF["path"]
        self.assertEqual([], sync.preserve_reviewed_v642_ui_scope(
            [path], sync.V642_UI_PROOF["base_commit"]))
        self.assertEqual([path], sync.preserve_reviewed_v642_ui_scope(
            [path], sync.V642_UI_PROOF["base_commit"], head="historical"))
        self.assertEqual(["unreviewed.py"], sync.preserve_reviewed_v642_ui_scope(
            ["unreviewed.py"], sync.V642_UI_PROOF["base_commit"]))

    def test_older_checker_edits_are_not_erased(self):
        import sync_v376_successor_test_support as sync
        path = sync.V642_UI_PROOF["path"]
        source = sync.V400_CANDIDATE
        prior = subprocess.check_output(["git", "diff", "--name-only",
            f'{source}..{sync.V642_UI_PROOF["base_commit"]}', "--", path],
            cwd=ROOT, text=True).splitlines()
        self.assertTrue(prior, "fixture must include independently reviewed older edits")
        self.assertEqual([path], sync.preserve_reviewed_v642_ui_scope([path], source))

    def test_modified_current_checker_is_never_delegated(self):
        import sync_v376_successor_test_support as sync
        original = Path.read_bytes
        def changed(path):
            return b"unreviewed" if path == ROOT / sync.V642_UI_PROOF["path"] else original(path)
        with unittest.mock.patch.object(Path, "read_bytes", changed):
            path = sync.V642_UI_PROOF["path"]
            self.assertEqual([path], sync.preserve_reviewed_v642_ui_scope(
                [path], sync.V642_UI_PROOF["base_commit"]))

    def test_proof_cannot_claim_device_installation(self):
        import sync_v376_successor_test_support as sync
        original = sync._read
        def forged(path):
            data = original(path)
            if path.name == "ui_dom_successor_v642.json":
                data["physical_tablet_runtime_verified"] = True
            return data
        with unittest.mock.patch.object(sync, "_read", forged):
            path = sync.V642_UI_PROOF["path"]
            self.assertEqual([path], sync.preserve_reviewed_v642_ui_scope(
                [path], sync.V642_UI_PROOF["base_commit"]))


class TabletBootSetupBehaviorTests(unittest.TestCase):
    def test_existing_installer_is_repeatable_and_quotes_device_paths(self):
        import os
        import tempfile
        source = (ROOT / "TABLET_SCHEDULED_UPDATE.sh").read_text(encoding="utf-8")
        # Execute the existing functions in an isolated fixture; no real loop,
        # network, Android package changes, or user boot directory is touched.
        source = source[:source.index('case "${1:-status}" in')]
        source = source.replace('${HOME}', '${TCG_TEST_HOME}')
        with tempfile.TemporaryDirectory(prefix="tcg boot path ") as tmp:
            fixture = Path(tmp)
            harness = fixture / "TABLET_SCHEDULED_UPDATE.sh"
            harness.write_text(source + '\nstart_loop_if_needed() { return 0; }\ntermux_boot_state() { echo detected; }\ninstall_schedule\nensure_schedule\n', encoding="utf-8")
            env = dict(os.environ, TCG_TEST_HOME=str(fixture / "test home"))
            result = subprocess.run(["bash", str(harness)], env=env, capture_output=True,
                                    text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            boot = fixture / "test home/.termux/boot/tcg-grader-scheduled-update.sh"
            self.assertTrue(boot.is_file())
            self.assertEqual(boot.stat().st_mode & 0o777, 0o700)
            subprocess.run(["bash", "-n", str(boot)], check=True, timeout=10)
            self.assertIn('exec bash "$ROOT/TABLET_SCHEDULED_UPDATE.sh" boot-loop',
                          boot.read_text(encoding="utf-8"))
            self.assertIn("Termux:Boot 감지", result.stdout)

    def test_missing_boot_app_is_reported_as_hold(self):
        import os
        import tempfile
        source = (ROOT / "TABLET_SCHEDULED_UPDATE.sh").read_text(encoding="utf-8")
        source = source[:source.index('case "${1:-status}" in')]
        source = source.replace('${HOME}', '${TCG_TEST_HOME}')
        with tempfile.TemporaryDirectory() as tmp:
            harness = Path(tmp) / "TABLET_SCHEDULED_UPDATE.sh"
            harness.write_text(source + '\nstart_loop_if_needed() { return 0; }\ntermux_boot_state() { echo not-detected; }\nensure_schedule\n', encoding="utf-8")
            result = subprocess.run(["bash", str(harness)],
                env=dict(os.environ, TCG_TEST_HOME=tmp), capture_output=True,
                text=True, timeout=10)
            self.assertEqual(result.returncode, 5)
            self.assertIn("HOLD", result.stderr)


if __name__ == "__main__":
    unittest.main()

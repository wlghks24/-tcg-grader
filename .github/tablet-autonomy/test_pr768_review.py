"""Fail-closed integrity checks for PR #768's evidence inventory."""
import json
import subprocess
import unittest
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
        from sync_v376_successor_test_support import (
            V426_CANDIDATE, V426_CONTRACT_PATH, _watched_paths,
            V427_WATCHED, V431_WATCHED, V432_WATCHED, V439_WATCHED,
            V440_WATCHED, V469_WATCHED, V470_WATCHED, V471_WATCHED,
            V480_WATCHED,
        )
        contract = json.loads(V426_CONTRACT_PATH.read_text(encoding="utf-8"))
        ancestor = subprocess.run(
            ["git", "cat-file", "-e", f"{V426_CANDIDATE}^{{commit}}"],
            cwd=ROOT, capture_output=True, check=False,
        )
        self.assertEqual(
            ancestor.returncode, 0,
            "V426 historical commit is required for the full-history PR768 gate; "
            "fetch history rather than skipping the comparison",
        )
        visible = set(_watched_paths(contract, V426_CANDIDATE))
        approved = set(V427_WATCHED + V431_WATCHED + V432_WATCHED +
                       V439_WATCHED + V440_WATCHED + V469_WATCHED +
                       V470_WATCHED + V471_WATCHED + V480_WATCHED)
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
        from sync_v376_successor_test_support import (
            V426_CANDIDATE, V426_CONTRACT_PATH, _watched_paths,
            V427_WATCHED, V431_WATCHED, V432_WATCHED, V439_WATCHED,
            V440_WATCHED, V469_WATCHED, V470_WATCHED, V471_WATCHED,
            V480_WATCHED,
        )
        review = json.loads(REVIEW.read_text(encoding="utf-8"))
        candidate = review["candidate_commit"]
        contract = json.loads(V426_CONTRACT_PATH.read_text(encoding="utf-8"))
        approved = set(V427_WATCHED + V431_WATCHED + V432_WATCHED +
                       V439_WATCHED + V440_WATCHED + V469_WATCHED +
                       V470_WATCHED + V471_WATCHED + V480_WATCHED)
        scope = set(_watched_paths(contract, V426_CANDIDATE)) - approved
        expected = {
            ".github/workflows/tablet-autonomy-patch-checks.yml",
            "tablet_autonomous_evolution_v372.py",
            "tablet_autonomous_evolution_v387.py",
        }
        self.assertEqual(scope, expected, "unreviewed watched paths must block")
        reviewed = {item["path"]: item["git_blob_sha"]
                    for item in review["reviewed_files"]}
        self.assertTrue(scope.issubset(reviewed))
        for path in sorted(scope):
            with self.subTest(path=path):
                current = subprocess.check_output(
                    ["git", "hash-object", "--", path], cwd=ROOT, text=True
                ).strip()
                self.assertEqual(current, reviewed[path],
                                 "successor scope has unreviewed bytes")
                prior = subprocess.run(
                    ["git", "diff", "--name-only",
                     f"{V426_CANDIDATE}..{candidate}^", "--", path],
                    cwd=ROOT, capture_output=True, text=True, check=False,
                )
                self.assertEqual(prior.returncode, 0,
                                 "cannot establish historical review boundary")
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


if __name__ == "__main__":
    unittest.main()

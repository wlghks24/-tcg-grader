"""Fail-closed integrity checks for PR #768's evidence inventory."""
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVIEW = Path(__file__).resolve().parent / "pr768_review.json"


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
        if ancestor.returncode != 0:
            shallow = subprocess.check_output(
                ["git", "rev-parse", "--is-shallow-repository"],
                cwd=ROOT, text=True,
            ).strip()
            self.assertEqual(shallow, "true",
                             "V426 history missing from non-shallow repository; fail closed")
            self.skipTest("V426 historical commit unavailable in shallow CI checkout; full-history alignment guard remains mandatory")
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

    def test_reviewed_blobs_are_exact_and_unchanged(self):
        data = json.loads(REVIEW.read_text(encoding="utf-8"))
        files = data["reviewed_files"]
        self.assertEqual(len(files), 4)
        paths = [item["path"] for item in files]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(set(paths), {
            "TABLET_SCHEDULED_UPDATE.sh",
            "tablet_autonomous_evolution_v372.py",
            "tablet_autonomous_evolution_v387.py",
            ".github/workflows/tablet-autonomy-patch-checks.yml",
        })
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
                self.assertEqual(actual, item["git_blob_sha"])


if __name__ == "__main__":
    unittest.main()

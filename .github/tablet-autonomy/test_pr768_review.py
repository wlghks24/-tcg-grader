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
        self.assertTrue(all(c in "0123456789abcdef" for c in data["candidate_commit"]))
        self.assertEqual(data["status"], "PENDING_SYNC_SUCCESSOR_AND_DEVICE_VALIDATION")
        self.assertIn("Exhaustive SELFREFINE Guard", data["blocked_checks"])
        self.assertIn("Tablet GPT TCG Grader Main Alignment", data["blocked_checks"])
        self.assertIn("Tablet Autonomy Patch Checks", data["verified_checks"])
        self.assertNotIn("Tablet GPT TCG Grader Main Alignment", data["verified_checks"])

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

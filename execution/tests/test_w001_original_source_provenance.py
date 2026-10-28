"""Read-only original Git source evidence checks for W001, not grading QA."""
from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = "6c78831bbb6e188717f86ef90243a836d2e0b67a"
GIT_ORIGIN = "6511c822f08685ab13ad3e2588d4bd093874c87b"
V99_ADDED = "d81711498eb05cfd84a007418cf389970b192197"
V291_REPAIRED = "70938e4ce0a99f74dba481eb317bb82e7b917e13"


def git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, timeout=25
    ).strip()


class W001OriginalSourceReviewTests(unittest.TestCase):
    def test_earliest_git_root_has_only_v31_era_files(self):
        parents = git("rev-list", "--parents", "-n", "1", GIT_ORIGIN).split()
        self.assertEqual([GIT_ORIGIN], parents)
        files = git("ls-tree", "-r", "--name-only", GIT_ORIGIN).splitlines()
        self.assertEqual(8, len(files))
        self.assertIn("README_v31.md", files)
        self.assertIn("tcg_updater.py", files)
        self.assertFalse(any(path.startswith("grading_accuracy_v99") for path in files))
        # This does NOT prove V001-V030 releases never existed.

    def test_historical_source_import_and_repair_commit_are_ancestors(self):
        for sha in (GIT_ORIGIN, V99_ADDED, V291_REPAIRED):
            with self.subTest(sha=sha):
                proc = subprocess.run(["git", "merge-base", "--is-ancestor",
                                       sha, BASE], cwd=ROOT, timeout=25)
                self.assertEqual(0, proc.returncode)

    def test_exact_v99_import_and_v291_repair_source_blobs(self):
        old = git("show", V99_ADDED + ":grading_accuracy_v99.py")
        repaired = git("show", V291_REPAIRED + ":grading_accuracy_v99.py")
        self.assertEqual("767d034edcf16c3fb1e0a4eba0c4520f5aa7a8a4",
                         git("rev-parse", V99_ADDED + ":grading_accuracy_v99.py"))
        self.assertEqual("fa9ec562983813276d40d71674f0dd7bf7e456a6",
                         git("rev-parse", V291_REPAIRED + ":grading_accuracy_v99.py"))
        self.assertIn("if x is not None:values.append(x*weight)", old)
        self.assertIn("if x is None:return 100", repaired)
        self.assertNotEqual(old, repaired)
        # Never invoke the imported historical grading module in this audit.

    def test_v100_synthetic_metrics_do_not_certify_photo_accuracy(self):
        raw = git("show", BASE + ":v100_reference/V100_FINAL_VERIFICATION_REPORT.json")
        report = json.loads(raw)
        self.assertEqual(6, report["successful_passes"])
        self.assertEqual(12, report["vision_self_learning"]["metrics"]["counts"]["tp"])
        self.assertEqual(24, report["vision_self_learning"]["metrics"]["counts"]["tn"])
        self.assertIs(report["vision_self_learning"]["calibration_adopted"], False)
        self.assertIs(report["safety"]["code_auto_modification"], False)
        self.assertTrue(any("synthetic" in item.lower() and "not a substitute" in item.lower()
                            for item in report["limitations"]))


if __name__ == "__main__":
    unittest.main()

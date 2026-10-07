#!/usr/bin/env python3
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from sync_v376_successor_test_support import assert_v440_successor

ROOT = Path(__file__).resolve().parent
C = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V440.json"
D = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v440_delta.json"
R = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v440.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class SyncV440(unittest.TestCase):
    def test_generation_digest_and_exact_scope(self):
        c, d, r = load(C), load(D), load(R)
        raw = json.dumps(d["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(d["lesson_digest_sha256"], hashlib.sha256(raw.encode("utf-8")).hexdigest())
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in d["lessons"]], r["accepted_lesson_ids"])
        self.assertEqual(["VERIFY_TABLET_FINAL.sh", "main"], c["candidate_sync"]["watched_paths"])
        self.assertTrue(c["candidate_sync"]["requires_exact_watched_path_match"])
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", c["candidate_sync"]["candidate_commit"], "HEAD"],
            check=True,
        )
        assert_v440_successor(self)

    def test_tablet_only_learning_safety_contract(self):
        d, r = load(D), load(R)
        main = (ROOT / "main").read_text(encoding="utf-8")
        schedule = (ROOT / "TABLET_SCHEDULED_UPDATE.sh").read_text(encoding="utf-8")
        verify = (ROOT / "VERIFY_TABLET_FINAL.sh").read_text(encoding="utf-8")
        command = (
            "tablet_autonomous_evolution_v400.py --domain tablet_gpt "
            "--execute-safe-learning --apply-capabilities --train-meta --apply-skills"
        )
        self.assertIn("tablet-learn|learn)", main)
        self.assertIn("learn-status)", main)
        self.assertIn(command, main)
        self.assertIn(command, schedule)
        self.assertIn("test_main_tablet_only_learning_v468.py", verify)
        self.assertFalse(d["share_policy"]["colab_required_for_tablet_learning"])
        self.assertFalse(d["share_policy"]["drive_required_for_tablet_learning"])
        self.assertFalse(d["share_policy"]["chatgpt_model_weights_exported"])
        self.assertFalse(d["share_policy"]["raw_grading_calibration_shared"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

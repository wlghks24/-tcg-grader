#!/usr/bin/env python3
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from sync_v376_successor_test_support import assert_v477_successor

ROOT = Path(__file__).resolve().parent
C = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V477.json"
D = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v477_delta.json"
R = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v477.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class SyncV477(unittest.TestCase):
    def test_generation_digest_and_exact_scope(self):
        c, d, r = load(C), load(D), load(R)
        raw = json.dumps(d["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(d["lesson_digest_sha256"], hashlib.sha256(raw.encode("utf-8")).hexdigest())
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in d["lessons"]], r["accepted_lesson_ids"])
        self.assertEqual(["main"], c["candidate_sync"]["watched_paths"])
        self.assertEqual(132, c["current_required_lesson_count"])
        subprocess.run(["git","merge-base","--is-ancestor",c["candidate_sync"]["candidate_commit"],"HEAD"],check=True)
        assert_v477_successor(self)

    def test_cleanup_is_bounded_and_local_only(self):
        d, r = load(D), load(R)
        main = (ROOT / "main").read_text(encoding="utf-8")
        block = main[main.index("  local-only|cloud-off)") : main.index("  recover)", main.index("  local-only|cloud-off)"))]
        self.assertIn('grep -Fv "TABLET_GDRIVE_SYNC.sh"', block)
        self.assertIn("00_TCG_GDRIVE_RECOVERY.sh", block)
        self.assertIn("TCG_GDRIVE_SYNC_BOOT.sh", block)
        self.assertNotRegex(block, r"(?m)^\\s*rclone\\b")
        self.assertNotIn("deletefile", block)
        self.assertNotIn("pkill", block)
        self.assertNotRegex(block, r"(?m)^\\s*kill\\b")
        self.assertTrue(d["share_policy"]["tablet_local_only_runtime"])
        self.assertFalse(d["share_policy"]["drive_files_deleted"])
        self.assertFalse(d["share_policy"]["rclone_configuration_deleted"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

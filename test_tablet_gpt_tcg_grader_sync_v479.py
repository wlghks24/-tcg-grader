#!/usr/bin/env python3
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from sync_v376_successor_test_support import assert_v479_successor

ROOT = Path(__file__).resolve().parent
C = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V479.json"
D = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v479_delta.json"
R = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v479.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class SyncV479(unittest.TestCase):
    def test_generation_digest_and_exact_scope(self):
        c, d, r = load(C), load(D), load(R)
        raw = json.dumps(d["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(d["lesson_digest_sha256"], hashlib.sha256(raw.encode("utf-8")).hexdigest())
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in d["lessons"]], r["accepted_lesson_ids"])
        self.assertEqual(sorted(["box_knowledge_stats.css","box_knowledge_stats.js"]), c["candidate_sync"]["watched_paths"])
        self.assertEqual(134, c["current_required_lesson_count"])
        subprocess.run(["git","merge-base","--is-ancestor",c["candidate_sync"]["candidate_commit"],"HEAD"],check=True)
        assert_v479_successor(self)

    def test_box_hit_refinement_is_verified_data_only(self):
        d, r = load(D), load(R)
        runtime = (ROOT / "box_knowledge_stats.js").read_text(encoding="utf-8")
        css = (ROOT / "box_knowledge_stats.css").read_text(encoding="utf-8")
        for token in ("boxKbFilterBar","boxKbGame","renderExpandedAnalysisFallback","selected==='ALL'||game===selected"):
            self.assertIn(token, runtime)
        self.assertIn("V479 tablet UI refinement", css)
        self.assertFalse(d["share_policy"]["non_core_grading_enabled"])
        self.assertFalse(d["share_policy"]["unverified_price_or_popularity_invention"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

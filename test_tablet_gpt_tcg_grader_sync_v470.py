#!/usr/bin/env python3
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from sync_v376_successor_test_support import assert_v470_successor

ROOT = Path(__file__).resolve().parent
C = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V470.json"
D = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v470_delta.json"
R = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v470.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class SyncV470(unittest.TestCase):
    def test_generation_digest_and_exact_scope(self):
        c, d, r = load(C), load(D), load(R)
        raw = json.dumps(d["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(d["lesson_digest_sha256"], hashlib.sha256(raw.encode("utf-8")).hexdigest())
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in d["lessons"]], r["accepted_lesson_ids"])
        self.assertEqual(["feature_category_nav.js"], c["candidate_sync"]["watched_paths"])
        self.assertEqual(130, c["current_required_lesson_count"])
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", c["candidate_sync"]["candidate_commit"], "HEAD"],
            check=True,
        )
        assert_v470_successor(self)

    def test_compact_category_flow_is_bounded_and_preserves_features(self):
        d, r = load(D), load(R)
        nav = (ROOT / "feature_category_nav.js").read_text(encoding="utf-8")
        css = (ROOT / "feature_category_nav.css").read_text(encoding="utf-8")
        self.assertTrue(d["share_policy"]["category_first_app_flow"])
        self.assertTrue(d["share_policy"]["one_detail_surface_at_a_time"])
        self.assertFalse(d["share_policy"]["arbitrary_selector_execution"])
        self.assertIn('categoryInteractionVersion: "v470-single-feature-view"', nav)
        self.assertIn('back.className = "app-feature-back"', nav)
        self.assertIn('collapse.className = "app-feature-collapse"', nav)
        self.assertIn(".app-feature-back", css)
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

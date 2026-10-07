#!/usr/bin/env python3
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from sync_v376_successor_test_support import assert_v471_successor

ROOT = Path(__file__).resolve().parent
C = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V471.json"
D = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v471_delta.json"
R = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v471.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class SyncV471(unittest.TestCase):
    def test_generation_digest_and_exact_scope(self):
        c, d, r = load(C), load(D), load(R)
        raw = json.dumps(d["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(d["lesson_digest_sha256"], hashlib.sha256(raw.encode("utf-8")).hexdigest())
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in d["lessons"]], r["accepted_lesson_ids"])
        self.assertEqual(["feature_category_nav.js"], c["candidate_sync"]["watched_paths"])
        self.assertEqual(131, c["current_required_lesson_count"])
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", c["candidate_sync"]["candidate_commit"], "HEAD"],
            check=True,
        )
        assert_v471_successor(self)

    def test_initial_category_only_state_is_explicit_and_bounded(self):
        d, r = load(D), load(R)
        nav = (ROOT / "feature_category_nav.js").read_text(encoding="utf-8")
        self.assertTrue(d["share_policy"]["initial_category_only_state"])
        self.assertTrue(d["share_policy"]["initial_managed_surfaces_hidden"])
        self.assertIn("  updateCategoryStatus(null);\n  setCategoryContent(null);\n", nav)
        self.assertIn("managedSurfaces.forEach((surface) => { surface.hidden = true; });", nav)
        self.assertIn('categoryInteractionVersion: "v470-single-feature-view"', nav)
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

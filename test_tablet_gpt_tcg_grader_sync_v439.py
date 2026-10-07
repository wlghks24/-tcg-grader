#!/usr/bin/env python3
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
C = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V439.json"
D = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v439_delta.json"
R = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v439.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

class SyncV439(unittest.TestCase):
    def test_digest_candidate_and_exact_scope(self):
        c, d, r = load(C), load(D), load(R)
        raw = json.dumps(d["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(d["lesson_digest_sha256"], hashlib.sha256(raw.encode("utf-8")).hexdigest())
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in d["lessons"]], r["accepted_lesson_ids"])
        self.assertEqual(
            [".github/workflows/tcg-autonomy-market-guard-v426.yml", "tablet_autonomy_dashboard_v400.js"],
            c["candidate_sync"]["watched_paths"],
        )
        self.assertTrue(c["candidate_sync"]["requires_exact_watched_path_match"])
        subprocess.run(["git", "merge-base", "--is-ancestor", c["candidate_sync"]["candidate_commit"], "HEAD"], check=True)

    def test_review_hardening_and_safety_boundaries(self):
        d, r = load(D), load(R)
        js = (ROOT / "tablet_autonomy_dashboard_v400.js").read_text(encoding="utf-8")
        state = js[js.index("function marketLensState(plan)"):js.index("function marketLensControls(")]
        workflow = (ROOT / ".github/workflows/tcg-autonomy-market-guard-v426.yml").read_text(encoding="utf-8")
        self.assertGreaterEqual(js.count("registryGameLabel("), 5)
        self.assertNotIn("safe.allowed_games", state)
        self.assertIn("test_tablet_registry_market_lens_v429.py", workflow)
        self.assertFalse(d["share_policy"]["profit_guarantee"])
        self.assertFalse(d["share_policy"]["market_direction_prediction"])
        self.assertTrue(d["share_policy"]["watch_purchase_and_grading_default_blocked"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])

if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from sync_v376_successor_test_support import assert_v480_successor

ROOT = Path(__file__).resolve().parent
C = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V480.json"
D = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v480_delta.json"
R = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v480.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class SyncV480(unittest.TestCase):
    def test_generation_digest_and_exact_scope(self):
        c, d, r = load(C), load(D), load(R)
        raw = json.dumps(d["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(d["lesson_digest_sha256"], hashlib.sha256(raw.encode("utf-8")).hexdigest())
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in d["lessons"]], r["accepted_lesson_ids"])
        self.assertEqual(sorted(["grade_market_flow.css","grade_market_flow.js","multi_market_price_collector.py","multi_market_prices.js","ui_app_shell_v272.css","ui_app_shell_v272.js"]), c["candidate_sync"]["watched_paths"])
        self.assertEqual(135, c["current_required_lesson_count"])
        subprocess.run(["git","merge-base","--is-ancestor",c["candidate_sync"]["candidate_commit"],"HEAD"],check=True)
        assert_v480_successor(self)

    def test_recommendation_remains_market_evidence_only(self):
        d, r = load(D), load(R)
        collector = (ROOT / "multi_market_price_collector.py").read_text(encoding="utf-8")
        flow = (ROOT / "grade_market_flow.js").read_text(encoding="utf-8")
        shell = (ROOT / "ui_app_shell_v272.js").read_text(encoding="utf-8")
        for token in (
            "_trade_recommendation",
            "independent source",
            "identity_ambiguous",
            "variant_ambiguous",
            "divergent_evidence",
        ):
            self.assertIn(token, collector)
        for token in ("agmRecommendedTrade","agmTradeSources","recommendationMatchesIdentity"):
            self.assertIn(token, flow)
        for token in ("gradeCockpitTrade","gradeCockpitTradeSources"):
            self.assertIn(token, shell)
        self.assertFalse(d["share_policy"]["profit_guarantee"])
        self.assertFalse(d["share_policy"]["grading_calibration_changed"])
        self.assertFalse(d["share_policy"]["non_core_grading_enabled"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

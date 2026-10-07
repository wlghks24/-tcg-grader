#!/usr/bin/env python3
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from sync_v376_successor_test_support import assert_v478_successor

ROOT = Path(__file__).resolve().parent
C = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V478.json"
D = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v478_delta.json"
R = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v478.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class SyncV478(unittest.TestCase):
    def test_generation_digest_and_exact_scope(self):
        c, d, r = load(C), load(D), load(R)
        raw = json.dumps(d["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(d["lesson_digest_sha256"], hashlib.sha256(raw.encode("utf-8")).hexdigest())
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in d["lessons"]], r["accepted_lesson_ids"])
        self.assertEqual(sorted(["box_hit_market_discovery.py","box_knowledge_stats.css","box_knowledge_stats.js","index.html","market_catalog_expander.js","update_promo_events.py","update_releases.py"]), c["candidate_sync"]["watched_paths"])
        self.assertEqual(133, c["current_required_lesson_count"])
        subprocess.run(["git","merge-base","--is-ancestor",c["candidate_sync"]["candidate_commit"],"HEAD"],check=True)
        assert_v478_successor(self)

    def test_expanded_data_surfaces_remain_verified_and_non_grading(self):
        d, r = load(D), load(R)
        release = (ROOT / "update_releases.py").read_text(encoding="utf-8")
        promo = (ROOT / "update_promo_events.py").read_text(encoding="utf-8")
        market = (ROOT / "box_hit_market_discovery.py").read_text(encoding="utf-8")
        box = (ROOT / "box_knowledge_stats.js").read_text(encoding="utf-8")
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("collect_registry_releases", release)
        self.assertIn("_registry_event_config", promo)
        self.assertIn("GAMES=_registry_games()", market)
        self.assertIn("boxKbGame", box)
        self.assertIn("coverageExpected", page)
        self.assertFalse(d["share_policy"]["non_core_grading_enabled"])
        self.assertFalse(d["share_policy"]["unverified_release_event_price_stock_invention"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

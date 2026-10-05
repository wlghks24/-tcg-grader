#!/usr/bin/env python3
import hashlib
import json
import unittest
from pathlib import Path
import tcg_game_registry as registry
from sync_v376_successor_test_support import assert_v427_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V427.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v427_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v427.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

class TabletGptTcgGraderSyncV427Tests(unittest.TestCase):
    def test_generation_and_digest(self):
        contract, delta, receipt = load(CONTRACT), load(DELTA), load(RECEIPT)
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(delta["lesson_digest_sha256"], hashlib.sha256(raw.encode("utf-8")).hexdigest())
        self.assertEqual(delta["lesson_digest_sha256"], receipt["delta_lesson_digest_sha256"])
        self.assertEqual(120, contract["prior_required_lesson_count"])
        self.assertEqual(1, contract["delta_required_lesson_count"])
        self.assertEqual(121, contract["current_required_lesson_count"])
        self.assertIn(453, contract["current_required_merge_prs"])
        assert_v427_successor(self)

    def test_wixoss_is_watch_only(self):
        data = registry.load_registry(ROOT)
        row = next(item for item in data["games"] if item["id"] == "wixoss")
        self.assertEqual("watch", row["state"])
        self.assertEqual(0, row["activation_score"])
        self.assertEqual(4673, row["evidence"]["marketplace_catalog_count"])
        self.assertTrue(row["evidence"]["official_live"])
        self.assertTrue(row["evidence"]["organized_play"])
        self.assertFalse(row["capabilities"]["grading"])
        self.assertEqual({"pokemon", "onepiece", "naruto"}, {r["id"] for r in registry.enabled_games("grading", root=ROOT)})
        self.assertFalse(data["policy"]["profit_guarantee"])
        self.assertFalse(data["policy"]["market_direction_prediction"])
        self.assertFalse(load(RECEIPT)["verification"]["physical_tablet_runtime_verified"])

if __name__ == "__main__":
    unittest.main(verbosity=2)

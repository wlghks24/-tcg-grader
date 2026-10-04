#!/usr/bin/env python3
import hashlib
import json
import unittest
from pathlib import Path

import tcg_category_autonomy as controller
import tcg_game_registry as registry

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V424.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v424_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v424.json"
BASE_SHA = "58cd34422347584d091c8c22ba9b44e0bd8a8b87"
CANDIDATE_SHA = "b82225032af589eae0738923918858caaa13edb0"
LESSON_IDS = ["TABLET-GPT-TCG-CATEGORY-AUTONOMY-REGISTRY-V424","TABLET-GPT-TCG-AUTONOMY-CONTROLLER-GATE-V424"]

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

class TabletGptTcgGraderSyncV424Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_lineage(self):
        contract, delta, receipt = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V423.json", contract["prior_contract"])
        self.assertEqual(BASE_SHA, delta["source_main_sha"])
        self.assertEqual(BASE_SHA, receipt["source_main_sha"])
        self.assertEqual(delta["lesson_digest_sha256"], digest(delta["lessons"]))
        self.assertEqual(delta["lesson_digest_sha256"], receipt["delta_lesson_digest_sha256"])
        self.assertEqual(LESSON_IDS, receipt["accepted_lesson_ids"])
        self.assertEqual(115, contract["prior_required_lesson_count"])
        self.assertEqual(2, contract["delta_required_lesson_count"])
        self.assertEqual(117, contract["current_required_lesson_count"])
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])

    def test_candidate_exactly_covers_tablet_category_autonomy(self):
        contract = load(CONTRACT)
        sync = contract["candidate_sync"]
        self.assertEqual(BASE_SHA, sync["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, sync["candidate_commit"])
        self.assertEqual([
            "TABLET_SCHEDULED_UPDATE.sh",
            "VERIFY_TABLET_FINAL.sh",
            "index.html",
            "main",
            "tablet_runtime_manifest.py",
            "tcg_category_autonomy.py",
            "tcg_category_autonomy_runtime.js",
        ], sync["watched_paths"])
        self.assertEqual(CANDIDATE_SHA, load(DELTA)["covered_merges"][0]["merge_sha"])

    def test_category_controller_is_fail_closed_and_registry_bound(self):
        report = controller.build_report(ROOT)
        self.assertEqual("ready", report["status"])
        self.assertEqual("routing_only", report["neural_controller"]["mode"])
        self.assertFalse(report["neural_controller"]["active"])
        self.assertEqual(1000, report["neural_controller"]["minimum_independent_labels"])
        self.assertFalse(report["safety_gates"]["source_code_auto_generation"])
        self.assertFalse(report["safety_gates"]["physical_tablet_runtime_verified"])
        data = registry.load_registry(ROOT)
        self.assertFalse(data["policy"]["profit_guarantee"])
        self.assertFalse(data["policy"]["market_direction_prediction"])
        self.assertTrue(data["policy"]["grading_requires_separate_calibration"])

if __name__ == "__main__":
    unittest.main(verbosity=2)

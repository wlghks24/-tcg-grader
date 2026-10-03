import hashlib
import json
import re
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v400 as autonomy
from sync_v376_successor_test_support import assert_v398_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V398.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v398_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v398.json"
BASE_SHA = "0777d51075fdba4a8e2d1ac5f3e99668c0380648"
CANDIDATE_SHA = "89fc0ed43a36918a62669fdc17e8bea1467e084d"
LESSON_ID = "TABLET-GPT-ADAPTIVE-COMPONENTS-V398"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV398Tests(unittest.TestCase):
    def test_generation_binding_digest_and_counts(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V397.json", c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v397_delta.json", c["prior_delta_snapshot"])
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(90, c["prior_required_lesson_count"])
        self.assertEqual(91, c["current_required_lesson_count"])
        self.assertEqual(410, c["current_required_merge_prs"][-1])
        self.assertEqual("SYNCED_VERIFIED", r["status"])

    def test_real_dom_category_and_feature_identity_contract(self):
        c = load(CONTRACT)
        for key in (
            "adaptive_category_keys_must_match_real_dom_required",
            "adaptive_feature_shortcut_identity_required",
            "adaptive_feature_shortcuts_existing_dom_only_required",
            "adaptive_feature_shortcuts_exact_allowlist_required",
            "adaptive_feature_shortcuts_user_restore_required",
            "adaptive_identity_drift_runtime_health_blocker_required",
            "adaptive_feature_market_activity_non_directional_only_required",
            "autonomous_source_code_generation_forbidden",
            "autonomous_git_write_forbidden",
            "market_direction_invention_forbidden",
        ):
            self.assertIs(c["rules"][key], True, key)
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        categories = re.findall(r'data-category-key="([^"]+)"', html)
        features = re.findall(r'data-feature-key="([^"]+)"', html)
        self.assertEqual(list(autonomy.CATEGORY_ORDER), categories)
        expected = [item for category in autonomy.CATEGORY_ORDER for item in autonomy.FEATURE_SHORTCUT_ORDER[category]]
        self.assertEqual(expected, features)
        self.assertEqual(18, len(features))
        self.assertEqual(18, len(set(features)))

    def test_candidate_exactly_covers_adaptive_component_change(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(["index.html","tablet_autonomous_evolution_v400.py","tablet_autonomy_dashboard_v400.css","tablet_autonomy_dashboard_v400.js"], candidate["watched_paths"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        assert_v398_successor(self)

    def test_receipt_preserves_physical_and_source_boundaries(self):
        r = load(RECEIPT)
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])
        self.assertTrue(r["alignment_policy"]["adaptive_feature_shortcuts_existing_dom_only"])
        self.assertTrue(r["alignment_policy"]["adaptive_identity_drift_runtime_health_blocker_required"])
        self.assertFalse(r["alignment_policy"]["source_code_auto_generation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

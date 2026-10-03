import hashlib
import json
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v400 as autonomy
from sync_v376_successor_test_support import assert_v393_successor

ROOT=Path(__file__).resolve().parent
CONTRACT=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V393.json"
DELTA=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT"/"learning_snapshot_v393_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK"/"TCG_GRADER"/"tablet_gpt_learning_receipt_v393.json"
BASE_SHA="06ac25a0982dec8d5dc0019fe1d2cd200ce5431d"
CANDIDATE_SHA="c9c3380935ccf5d3cda40b2932020e9389ff53ff"
LESSON_ID="TABLET-GPT-DOMAIN-AWARE-VERIFIED-SELF-EVOLUTION-V400"
EXPECTED_WATCHED=[
    "VERIFY_TABLET_FINAL.sh",
    "index.html",
    "main",
    "sw.js",
    "tablet_autonomous_evolution_v398.py",
    "tablet_autonomous_evolution_v400.py",
    "tablet_autonomy_dashboard_v400.css",
    "tablet_autonomy_dashboard_v400.js",
    "tablet_runtime_manifest.py",
    "tcg_updater.py",
]

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def digest(value):
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV393Tests(unittest.TestCase):
    def test_generation_binding_digest_and_counts(self):
        c,d,r=load(CONTRACT),load(DELTA),load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V392.json",c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v392_delta.json",c["prior_delta_snapshot"])
        self.assertEqual(BASE_SHA,d["source_main_sha"])
        self.assertEqual(BASE_SHA,r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"],digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID],r["accepted_lesson_ids"])
        self.assertEqual(85,c["prior_required_lesson_count"])
        self.assertEqual(86,c["current_required_lesson_count"])
        self.assertEqual("SYNCED_VERIFIED",r["status"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])

    def test_v400_rules_and_safety(self):
        c=load(CONTRACT)
        for key in (
            "domain_surface_portfolio_required",
            "surface_evidence_confidence_required",
            "missing_surface_evidence_revalidation_required",
            "ui_surface_governance_required",
            "card_measurement_verified_evidence_required",
            "card_market_freshness_source_health_required",
            "collab_event_coverage_source_health_required",
            "surface_goal_self_selection_required",
            "v400_owned_single_canary_required",
            "v400_canonical_v373_allowlist_required",
            "v397_v398_v400_experiment_conflict_required",
            "surface_verified_gain_release_required",
            "surface_material_regression_exact_rollback_required",
            "surface_source_feature_non_executable_required",
            "surface_source_feature_protected_pr_ci_required",
            "price_grade_event_fact_invention_forbidden",
            "v399_gate_cannot_be_bypassed",
            "v398_gate_cannot_be_bypassed",
        ):
            self.assertIs(c["rules"][key],True,key)
        self.assertTrue(autonomy.SAFETY["ui_card_measurement_market_event_governance_enabled"])
        self.assertTrue(autonomy.SAFETY["surface_runtime_self_extension_allowlisted_only"])
        self.assertTrue(autonomy.SAFETY["surface_source_feature_candidates_non_executable"])
        self.assertTrue(autonomy.SAFETY["v399_gate_cannot_be_bypassed"])
        self.assertTrue(autonomy.SAFETY["v398_gate_cannot_be_bypassed"])
        self.assertFalse(autonomy.SAFETY["card_measurement_grade_invention"])
        self.assertFalse(autonomy.SAFETY["card_market_price_invention"])
        self.assertFalse(autonomy.SAFETY["event_fact_invention"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["git_write"])

    def test_candidate_exactly_covers_v400_route(self):
        c=load(CONTRACT)
        candidate=c["candidate_sync"]
        self.assertEqual(BASE_SHA,candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA,candidate["candidate_commit"])
        self.assertEqual(EXPECTED_WATCHED,candidate["watched_paths"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        assert_v393_successor(self)

    def test_current_runtime_and_dashboard_use_v400(self):
        main=(ROOT/"main").read_text(encoding="utf-8")
        manifest=(ROOT/"tablet_runtime_manifest.py").read_text(encoding="utf-8")
        index=(ROOT/"index.html").read_text(encoding="utf-8")
        sw=(ROOT/"sw.js").read_text(encoding="utf-8")
        updater=(ROOT/"tcg_updater.py").read_text(encoding="utf-8")
        self.assertIn(
            "tablet_autonomous_evolution_v400.py --domain tablet_gpt --execute-safe-learning --apply-capabilities --train-meta --apply-skills",
            main,
        )
        for version in ("v400","v399","v398","v397","v391","v390","v388","v387","v386","v385","v382","v381","v380","v379","v378","v377","v376"):
            self.assertIn(f'"tablet_autonomous_evolution_{version}.py"',manifest)
        for asset in ("tablet_autonomy_dashboard_v400.js","tablet_autonomy_dashboard_v400.css"):
            self.assertIn(asset,manifest)
            self.assertIn(asset,index)
            self.assertIn(asset,sw)
            self.assertIn(asset,updater)
        self.assertIn("tablet_autonomy_v400_report.json",updater)
        self.assertNotIn("tablet_autonomy_v400_report.json",sw)

    def test_receipt_preserves_device_source_and_fact_boundaries(self):
        r=load(RECEIPT)
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])
        self.assertTrue(r["alignment_policy"]["domain_surface_portfolio_required"])
        self.assertTrue(r["alignment_policy"]["surface_evidence_confidence_required"])
        self.assertTrue(r["alignment_policy"]["missing_surface_evidence_revalidation_required"])
        self.assertTrue(r["alignment_policy"]["v400_canonical_v373_allowlist_required"])
        self.assertFalse(r["alignment_policy"]["source_feature_runtime_execution"])
        self.assertFalse(r["alignment_policy"]["source_code_auto_generation"])
        self.assertFalse(r["alignment_policy"]["price_grade_event_fact_invention"])
        self.assertTrue(r["alignment_policy"]["read_only_autonomy_dashboard"])


if __name__=="__main__":
    unittest.main(verbosity=2)

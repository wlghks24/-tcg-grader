import hashlib
import json
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v399 as autonomy
from sync_v376_successor_test_support import assert_v392_successor

ROOT=Path(__file__).resolve().parent
CONTRACT=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V392.json"
DELTA=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT"/"learning_snapshot_v392_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK"/"TCG_GRADER"/"tablet_gpt_learning_receipt_v392.json"
BASE_SHA="62bc132373bc9dafb88d9057e8b3c54c2c388fea"
CANDIDATE_SHA="e491ff1c64c30f6d72d33ee33999f937cf82e1e6"
LESSON_ID="TABLET-GPT-CROSS-SURFACE-UI-PWA-SELF-EVOLUTION-V399"
EXPECTED_WATCHED=[
    "VERIFY_TABLET_FINAL.sh",
    "index.html",
    "main",
    "sw.js",
    "tablet_autonomous_evolution_v399.py",
    "tablet_autonomy_dashboard_v399.css",
    "tablet_autonomy_dashboard_v399.js",
    "tablet_runtime_manifest.py",
    "tcg_updater.py",
]

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def digest(value):
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV392Tests(unittest.TestCase):
    def test_generation_binding_digest_and_counts(self):
        c,d,r=load(CONTRACT),load(DELTA),load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V391.json",c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v391_delta.json",c["prior_delta_snapshot"])
        self.assertEqual(BASE_SHA,d["source_main_sha"])
        self.assertEqual(BASE_SHA,r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"],digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID],r["accepted_lesson_ids"])
        self.assertEqual(84,c["prior_required_lesson_count"])
        self.assertEqual(85,c["current_required_lesson_count"])
        self.assertEqual(403,c["current_required_merge_prs"][-1])
        self.assertEqual("SYNCED_VERIFIED",r["status"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])

    def test_v399_rules_and_safety(self):
        c=load(CONTRACT)
        for key in (
            "cross_surface_self_diagnosis_required",
            "ui_ux_pwa_runtime_health_governance_required",
            "ui_gap_recurrence_learning_required",
            "ui_source_feature_candidate_non_executable_required",
            "ui_source_feature_protected_pr_ci_required",
            "runtime_ui_source_auto_rewrite_forbidden",
            "read_only_autonomy_dashboard_required",
            "dashboard_report_live_static_exposure_required",
            "v398_gate_cannot_be_bypassed",
            "autonomous_source_code_generation_forbidden",
            "autonomous_git_write_forbidden",
            "autonomous_verification_bypass_forbidden",
            "market_direction_invention_forbidden",
        ):
            self.assertIs(c["rules"][key],True,key)
        self.assertTrue(autonomy.SAFETY["cross_surface_self_diagnosis_enabled"])
        self.assertTrue(autonomy.SAFETY["ui_gap_recurrence_learning_enabled"])
        self.assertTrue(autonomy.SAFETY["ui_source_feature_candidates_non_executable"])
        self.assertTrue(autonomy.SAFETY["v398_gate_cannot_be_bypassed"])
        self.assertFalse(autonomy.SAFETY["runtime_source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["runtime_source_code_auto_rewrite"])
        self.assertFalse(autonomy.SAFETY["runtime_ui_source_auto_rewrite"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_candidate_exactly_covers_v399_cross_surface_route(self):
        c=load(CONTRACT)
        candidate=c["candidate_sync"]
        self.assertEqual(BASE_SHA,candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA,candidate["candidate_commit"])
        self.assertEqual(EXPECTED_WATCHED,candidate["watched_paths"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        self.assertIn("VERIFY_TABLET_FINAL.sh",c["freshness_watch"]["exact_paths"])
        assert_v392_successor(self)

    def test_current_runtime_delegates_to_v400_successor(self):
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

    def test_receipt_preserves_device_source_and_ui_boundaries(self):
        r=load(RECEIPT)
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])
        self.assertTrue(r["alignment_policy"]["v398_gate_cannot_be_bypassed"])
        self.assertTrue(r["alignment_policy"]["cross_surface_self_diagnosis_required"])
        self.assertTrue(r["alignment_policy"]["ui_pwa_runtime_health_required"])
        self.assertTrue(r["alignment_policy"]["ui_gap_recurrence_learning_only"])
        self.assertFalse(r["alignment_policy"]["ui_source_feature_runtime_execution"])
        self.assertFalse(r["alignment_policy"]["runtime_ui_source_auto_rewrite"])
        self.assertTrue(r["alignment_policy"]["read_only_autonomy_dashboard"])


if __name__=="__main__":
    unittest.main(verbosity=2)

import hashlib
import json
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v397 as autonomy
from sync_v376_successor_test_support import assert_v390_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V390.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v390_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v390.json"
BASE_SHA = "8701be1d348cb024e9c9675d4fb0eb3034a75d9d"
CANDIDATE_SHA = "fff9ed46696f7b9148c61c60f97f62a820527fa7"
LESSON_ID = "TABLET-GPT-BOUNDED-SELF-EXTENSION-ROLLBACK-V397"
EXPECTED_WATCHED = ["main", "tablet_autonomous_evolution_v397.py", "tablet_runtime_manifest.py"]

def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))

def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

class TabletGptTcgGraderSyncV390Tests(unittest.TestCase):
    def test_generation_binding_digest_and_counts(self):
        c,d,r=load(CONTRACT),load(DELTA),load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V389.json",c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v389_delta.json",c["prior_delta_snapshot"])
        self.assertEqual(BASE_SHA,d["source_main_sha"])
        self.assertEqual(BASE_SHA,r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"],digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID],r["accepted_lesson_ids"])
        self.assertEqual(82,c["prior_required_lesson_count"])
        self.assertEqual(83,c["current_required_lesson_count"])
        self.assertEqual(398,c["current_required_merge_prs"][-1])
        self.assertEqual("SYNCED_VERIFIED",r["status"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])

    def test_v397_rules_preserve_fail_closed_owned_self_extension(self):
        c=load(CONTRACT)
        for key in (
            "v391_gate_cannot_be_bypassed",
            "v390_gate_cannot_be_bypassed",
            "operational_mode_self_selection_required",
            "market_flow_operational_only_required",
            "one_owned_declarative_capability_at_a_time_required",
            "owned_capability_canonical_v373_allowlist_required",
            "owned_capability_next_cycle_only_required",
            "owned_capability_baseline_kpi_required",
            "owned_capability_exact_rollback_required",
            "owned_capability_upstream_hold_rollback_required",
            "owned_capability_material_kpi_regression_rollback_required",
            "v391_v390_competing_capability_write_forbidden",
            "verified_canary_source_promotion_required",
            "positive_verified_kpi_delta_source_promotion_required",
            "verified_output_source_promotion_required",
            "source_feature_protected_pr_candidate_non_executable_required",
            "autonomous_source_code_generation_forbidden",
            "autonomous_git_write_forbidden",
            "autonomous_verification_bypass_forbidden",
            "market_direction_invention_forbidden",
        ):
            self.assertIs(c["rules"][key],True,key)
        self.assertTrue(autonomy.SAFETY["declarative_self_extension_enabled"])
        self.assertTrue(autonomy.SAFETY["owned_capability_auto_rollback_enabled"])
        self.assertTrue(autonomy.SAFETY["source_feature_verified_canary_required"])
        self.assertTrue(autonomy.SAFETY["v391_gate_cannot_be_bypassed"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_candidate_exactly_covers_v397_runtime_route(self):
        c=load(CONTRACT)
        candidate=c["candidate_sync"]
        self.assertEqual(BASE_SHA,candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA,candidate["candidate_commit"])
        self.assertEqual(EXPECTED_WATCHED,candidate["watched_paths"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        assert_v390_successor(self)

    def test_main_and_runtime_manifest_use_v397(self):
        main=(ROOT/"main").read_text(encoding="utf-8")
        manifest=(ROOT/"tablet_runtime_manifest.py").read_text(encoding="utf-8")
        self.assertIn(
            "tablet_autonomous_evolution_v399.py --domain tablet_gpt --execute-safe-learning --apply-capabilities --train-meta --apply-skills",
            main,
        )
        for version in ("v397","v391","v390","v388","v387","v386","v385","v382","v381","v380","v379","v378","v377","v376"):
            self.assertIn(f'"tablet_autonomous_evolution_{version}.py"',manifest)

    def test_receipt_preserves_device_and_source_boundaries(self):
        r=load(RECEIPT)
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])
        self.assertTrue(r["alignment_policy"]["owned_capability_canonical_allowlist_only"])
        self.assertTrue(r["alignment_policy"]["owned_capability_one_at_a_time"])
        self.assertTrue(r["alignment_policy"]["owned_capability_exact_rollback"])
        self.assertTrue(r["alignment_policy"]["verified_canary_source_promotion_required"])
        self.assertFalse(r["alignment_policy"]["source_feature_runtime_code_generation"])

if __name__=="__main__":
    unittest.main(verbosity=2)

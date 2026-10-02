import hashlib
import json
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v388 as autonomy
from sync_v376_successor_test_support import assert_v387_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V387.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v387_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v387.json"
BASE_SHA = "b5b100f93e8180e81458612b450f9411546463bf"
CANDIDATE_SHA = "541e8835a93f2534fe49b0fe69ea762a1d897b63"
LESSON_ID = "TABLET-GPT-TCG-GRADER-REGIME-POLICY-PORTFOLIO-AUTONOMY-V388"
EXPECTED_WATCHED = ["main", "tablet_autonomous_evolution_v388.py", "tablet_runtime_manifest.py"]


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV387Tests(unittest.TestCase):
    def test_generation_binding_digest_and_counts(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual(
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V386.json",
            c["prior_contract"],
        )
        self.assertEqual(
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v386_delta.json",
            c["prior_delta_snapshot"],
        )
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(79, c["prior_required_lesson_count"])
        self.assertEqual(80, c["current_required_lesson_count"])
        self.assertEqual(385, c["current_required_merge_prs"][-1])
        self.assertEqual("SYNCED_VERIFIED", r["status"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])

    def test_v388_rules_preserve_fail_closed_portfolio_autonomy(self):
        c = load(CONTRACT)
        for key in (
            "regime_conditioned_policy_portfolio_required",
            "verified_reward_portfolio_memory_only",
            "short_long_horizon_reward_tracking_required",
            "conservative_reward_lower_confidence_bound_required",
            "verified_policy_regression_quarantine_required",
            "verified_policy_regression_retirement_required",
            "recovery_policy_not_quarantined_by_portfolio_required",
            "resource_budget_autonomy_required",
            "exploration_budget_advisory_only_required",
            "feature_backlog_autoprioritization_required",
            "feature_backlog_non_executable_required",
            "v387_gate_cannot_be_bypassed",
            "autonomous_source_code_generation_forbidden",
            "autonomous_git_write_forbidden",
            "autonomous_verification_bypass_forbidden",
            "market_direction_invention_forbidden",
        ):
            self.assertIs(c["rules"][key], True, key)

        self.assertTrue(autonomy.SAFETY["regime_conditioned_policy_portfolio"])
        self.assertTrue(autonomy.SAFETY["verified_reward_memory_only"])
        self.assertTrue(autonomy.SAFETY["resource_budget_autonomy"])
        self.assertTrue(autonomy.SAFETY["feature_backlog_non_executable"])
        self.assertTrue(autonomy.SAFETY["v387_gate_cannot_be_bypassed"])
        self.assertFalse(autonomy.SAFETY["peer_model_weights_imported"])
        self.assertFalse(autonomy.SAFETY["peer_raw_state_imported"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_rewrite"])
        self.assertFalse(autonomy.SAFETY["arbitrary_command_execution"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_candidate_exactly_covers_current_v388_route(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(EXPECTED_WATCHED, candidate["watched_paths"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        assert_v387_successor(self)

    def test_main_and_runtime_manifest_use_v388(self):
        main = (ROOT / "main").read_text(encoding="utf-8")
        manifest = (ROOT / "tablet_runtime_manifest.py").read_text(encoding="utf-8")
        self.assertIn(
            "tablet_autonomous_evolution_v398.py --domain tablet_gpt --execute-safe-learning --apply-capabilities --train-meta --apply-skills",
            main,
        )
        for version in ("v397", "v391", "v390", "v388", "v387", "v386", "v385", "v382", "v381", "v380", "v379", "v378", "v377", "v376"):
            self.assertIn(f'"tablet_autonomous_evolution_{version}.py"', manifest)

    def test_receipt_keeps_device_and_source_boundaries(self):
        r = load(RECEIPT)
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])
        self.assertTrue(r["alignment_policy"]["verified_reward_portfolio_only"])
        self.assertTrue(r["alignment_policy"]["exploration_budget_advisory_only"])
        self.assertTrue(r["alignment_policy"]["source_feature_backlog_non_executable"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

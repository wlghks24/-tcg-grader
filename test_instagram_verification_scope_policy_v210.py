#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from pathlib import Path

from code_map_intelligence import resolve_feature_query

ROOT = Path(__file__).resolve().parent
POLICY = ROOT / "instagram_tcg_content" / "verification_scope_policy.json"
README = ROOT / "instagram_tcg_content" / "README.md"
IG_WORKFLOW = ROOT / ".github" / "workflows" / "instagram-tcg-selfrefine.yml"
LEGACY_WORKFLOW = ROOT / ".github" / "workflows" / "daily-0600-collection-instagram-accuracy.yml"
LEGACY_PERSIST = ROOT / ".github" / "workflows" / "persist-main-crosscheck-snapshot.yml"


class InstagramVerificationScopePolicyV210Tests(unittest.TestCase):
    def test_policy_is_instagram_local_only(self):
        payload = json.loads(POLICY.read_text(encoding="utf-8"))
        self.assertEqual(payload["project"], "instagram_card")
        self.assertEqual(
            payload["task_id"],
            "6a9b8a22e72c8191849c273e1240378e",
        )
        self.assertEqual(payload["room_scope"], "instagram_cardinfo")
        self.assertEqual(payload["verification_mode"], "INSTAGRAM_LOCAL_EVIDENCE_ONLY")
        self.assertFalse(payload["card_price_analysis_used"])
        self.assertFalse(payload["market_analysis_snapshot_crosscheck_enabled"])
        self.assertFalse(payload["market_analysis_peer_learning_enabled"])
        self.assertFalse(payload["cross_domain_runtime_bridge_enabled"])
        self.assertFalse(payload["market_analysis_snapshot_write_enabled"])
        self.assertEqual(payload["legacy_main_snapshot_persistence_mode"], "DISABLED_NOOP_MANUAL_ONLY")
        self.assertTrue(payload["fail_closed"])
        self.assertEqual(
            payload["source_verification_entrypoint"],
            "instagram_tcg_content/source_verification_engine.py",
        )
        self.assertEqual(
            payload["collection_freshness_gap_entrypoint"],
            "instagram_tcg_content/collection_freshness_gap_guard.py",
        )
        self.assertTrue(payload["shared_collection_freshness_diagnostic_only"])
        self.assertFalse(payload["shared_collection_verification_authority"])
        self.assertFalse(payload["shared_collection_direct_fact_promotion_allowed"])
        self.assertIn(
            "shared_collection_freshness_diagnostic_only",
            payload["preproduction_order"],
        )
        self.assertTrue(payload["user_requested_recovery_can_use_verified_missed_slot_evidence"])
        self.assertTrue(
            payload["user_requested_recovery_missed_slot_evidence_does_not_backfill_blocked_attempt"]
        )
        self.assertTrue(payload["user_requested_recovery_still_requires_no_finalized_record"])
        self.assertEqual(payload["user_requested_recovery_max_attempts_per_day"], 1)
        self.assertTrue(payload["production_verification_receipt_required"])
        self.assertEqual(
            payload["production_verification_receipt_mode"],
            "INSTAGRAM_LOCAL_EVIDENCE_ONLY",
        )
        self.assertEqual(
            payload["production_finalization_entrypoint"],
            "instagram_tcg_content/production_state.py::finalize_production",
        )
        self.assertEqual(payload["production_verification_receipt_schema"], 2)
        self.assertEqual(
            payload["production_verification_receipt_contract"],
            "OBSERVATION_GROUPS_V1",
        )
        self.assertEqual(
            payload["production_verification_receipt_input"],
            "RAW_OBSERVATION_GROUPS_ONLY",
        )
        self.assertTrue(
            payload["production_verification_receipt_observation_fingerprint_required"]
        )
        self.assertTrue(payload["production_snapshot_sha256_required"])
        self.assertTrue(payload["production_receipt_snapshot_hash_match_required"])
        self.assertEqual(payload["completed_sale_capture_max_hours"], 36)
        self.assertEqual(payload["completed_sale_event_max_days"], 30)
        self.assertEqual(payload["completed_sale_min_independent_sources"], 2)
        self.assertIn("build_verification_receipt", payload["preproduction_order"])
        self.assertIn("validate_verification_receipt", payload["preproduction_order"])

    def test_readme_does_not_reintroduce_main_crosscheck(self):
        text = README.read_text(encoding="utf-8")
        self.assertNotIn("crosscheck_exchange/를 통한 passive factual JSON 교차검증만 허용", text)
        self.assertNotIn("TCG_CROSSCHECK/exchange_manifest.json", text)
        self.assertIn("Main/카드시세분석 factual snapshot", text)
        self.assertIn("raw Observation", text)
        self.assertIn("observation_fingerprint", text)
        self.assertIn("snapshot_id/hash", text)

    def test_instagram_ci_does_not_execute_market_analysis_crosscheck(self):
        text = IG_WORKFLOW.read_text(encoding="utf-8")
        forbidden = (
            "crosscheck_runtime_bridge.py",
            "peer_learning_runtime_bridge.py",
            "main_persisted_crosscheck_export.py",
            "main_persisted_learning_export.py",
            "TCG_CROSSCHECK/MARKET_ANALYSIS",
            "daily_collection_instagram_accuracy.py",
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, text)
        self.assertIn("test_source_verification_engine", text)
        self.assertIn("test_source_route_resilience", text)
        self.assertIn("collection_freshness_gap_guard --self-test", text)
        self.assertIn("test_collection_freshness_gap_guard", text)

    def test_legacy_cross_domain_workflow_is_noop_and_unscheduled(self):
        text = LEGACY_WORKFLOW.read_text(encoding="utf-8")
        trigger_text = text.split("\npermissions:", 1)[0]
        self.assertNotIn("schedule:", trigger_text)
        self.assertNotIn("pull_request:", trigger_text)
        self.assertNotIn("push:", trigger_text)
        self.assertIn("workflow_dispatch:", trigger_text)
        self.assertNotIn("python crosscheck_runtime_bridge.py", text)
        self.assertIn("Cross-domain audit retired", text)

    def test_legacy_main_snapshot_persistence_is_noop_and_read_only(self):
        text = LEGACY_PERSIST.read_text(encoding="utf-8")
        trigger_text = text.split("\npermissions:", 1)[0]
        self.assertNotIn("workflow_run:", trigger_text)
        self.assertNotIn("schedule:", trigger_text)
        self.assertNotIn("push:", trigger_text)
        self.assertIn("workflow_dispatch:", trigger_text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("MARKET_ANALYSIS/factual_snapshot.json", text)
        self.assertNotIn("main-crosscheck-snapshot", text)
        self.assertIn("Main snapshot persistence retired", text)

    def test_code_map_routes_crosscheck_wording_to_local_verifier(self):
        result = resolve_feature_query("인스타 카드정보 자료 비교 교차확인 오류")
        self.assertEqual(result["entry_group"], "instagram_cardinfo_crosscheck")
        self.assertEqual(
            result["entry_file"],
            "instagram_tcg_content/source_verification_engine.py",
        )
        self.assertNotIn("crosscheck_runtime_bridge.py", result["primary_files"])
        self.assertNotIn("test_crosscheck_runtime_bridge_v26.py", result["suggested_tests"])


if __name__ == "__main__":
    unittest.main()

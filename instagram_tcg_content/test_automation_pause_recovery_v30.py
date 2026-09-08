#!/usr/bin/env python3
from __future__ import annotations

import unittest

from instagram_tcg_content.automation_state_guard import (
    AutomationStateGuardError,
    CANONICAL_ID,
    CANONICAL_TITLE,
    classify_pause,
    runtime_failure_policy,
)


class AutomationPauseRecoveryV30Tests(unittest.TestCase):
    def state(self, enabled: bool = False) -> dict:
        return {
            "id": CANONICAL_ID,
            "title": CANONICAL_TITLE,
            "is_enabled": enabled,
            "updated_at": "2026-09-06T20:34:07.836996Z",
            "last_run_time": "2026-09-06T19:30:22.873339Z",
        }

    def test_unknown_pause_never_fabricates_root_cause(self):
        result = classify_pause(
            self.state(False),
            observed_at="2026-09-07T01:01:48.674172Z",
        )
        self.assertTrue(result["pause_detected"])
        self.assertEqual(result["cause_status"], "unresolved")
        self.assertEqual(result["cause_class"], "CONTROL_PLANE_ATTRIBUTION_UNAVAILABLE")
        self.assertFalse(result["root_cause_fabricated"])
        self.assertEqual(result["required_action"], "REACTIVATE_EXISTING_CANONICAL_AUTOMATION")
        self.assertFalse(result["new_automation_allowed"])
        self.assertTrue(result["runtime_failure_must_not_disable_automation"])

    def test_recurrent_pause_is_critical_without_inventing_cause(self):
        result = classify_pause(
            self.state(False),
            observed_at="2026-09-07T01:01:48.674172Z",
            prior_pause_count=1,
        )
        self.assertEqual(result["recurrence_count"], 2)
        self.assertEqual(result["severity"], "PAUSE_RECURRENCE_CRITICAL")
        self.assertEqual(result["cause_class"], "CONTROL_PLANE_ATTRIBUTION_UNAVAILABLE")

    def test_schedule_start_disable_without_run_is_fingerprinted_not_attributed(self):
        state = self.state(False)
        state["updated_at"] = "2026-09-08T01:37:01.377102Z"
        state["last_run_time"] = "2026-09-07T20:27:56.644698Z"
        result = classify_pause(
            state,
            observed_at="2026-09-08T05:44:00Z",
            prior_pause_count=2,
        )
        self.assertEqual(
            result["state_transition_fingerprint"],
            "SCHEDULE_START_DISABLE_WITHOUT_RUN",
        )
        self.assertTrue(result["schedule_start_disable_without_run"])
        self.assertEqual(result["schedule_start_slot_kst"], "2026-09-08T10:30+09:00")
        self.assertFalse(result["state_transition_is_root_cause"])
        self.assertEqual(result["cause_status"], "unresolved")
        self.assertEqual(result["cause_class"], "CONTROL_PLANE_ATTRIBUTION_UNAVAILABLE")
        self.assertEqual(result["recurrence_count"], 3)
        self.assertEqual(result["severity"], "PAUSE_RECURRENCE_CRITICAL")

    def test_missed_slots_anchor_to_last_run_not_disable_time(self):
        state = self.state(False)
        state["updated_at"] = "2026-09-08T01:37:01.377102Z"
        state["last_run_time"] = "2026-09-07T20:27:56.644698Z"
        result = classify_pause(
            state,
            observed_at="2026-09-08T05:44:00Z",
            prior_pause_count=2,
        )
        self.assertEqual(result["missed_slot_anchor"], "last_run_plus_early_grace")
        self.assertEqual(result["schedule_run_early_grace_minutes"], 5)
        self.assertIn("2026-09-08T06:30+09:00", result["missed_slots_kst"])
        self.assertIn("2026-09-08T10:30+09:00", result["missed_slots_kst"])
        self.assertNotIn("2026-09-08T05:30+09:00", result["missed_slots_kst"])
        self.assertTrue(result["missed_full_0630"])
        self.assertEqual(
            result["catchup_policy"],
            "AT_MOST_ONCE_SAME_DAY_WITHOUT_BASELINE_CREATION",
        )

    def test_evidence_backed_reason_is_preserved(self):
        result = classify_pause(
            self.state(False),
            observed_at="2026-09-07T01:01:48.674172Z",
            cause_evidence={
                "actor": "user",
                "reason": "manual pause",
                "cause_class": "EXPLICIT_USER_PAUSE",
            },
        )
        self.assertEqual(result["cause_status"], "evidence_backed")
        self.assertEqual(result["cause_class"], "EXPLICIT_USER_PAUSE")
        self.assertEqual(result["cause_actor"], "user")
        self.assertEqual(result["cause_reason"], "manual pause")

    def test_0630_missed_slot_requests_bounded_catchup(self):
        result = classify_pause(
            self.state(False),
            observed_at="2026-09-07T01:01:48.674172Z",
        )
        self.assertTrue(result["missed_full_0630"])
        self.assertEqual(
            result["catchup_policy"],
            "AT_MOST_ONCE_SAME_DAY_WITHOUT_BASELINE_CREATION",
        )

    def test_enabled_state_is_not_pause_incident(self):
        result = classify_pause(
            self.state(True),
            observed_at="2026-09-07T01:01:48.674172Z",
        )
        self.assertFalse(result["pause_detected"])
        self.assertEqual(result["required_action"], "NONE")
        self.assertTrue(result["desired_enabled_state"])

    def test_runtime_failure_policy_never_disables_scheduler(self):
        policy = runtime_failure_policy(
            stage="render",
            error_code="ARTIFACT_GENERATION_FAILED",
            retryable=False,
        )
        self.assertEqual(policy["run_status"], "BLOCKED")
        self.assertFalse(policy["automation_state_mutation_allowed"])
        self.assertFalse(policy["self_disable_allowed"])
        self.assertFalse(policy["self_pause_allowed"])
        self.assertFalse(policy["self_reschedule_allowed"])
        self.assertTrue(policy["preserve_enabled_state"])
        self.assertTrue(policy["preserve_schedule"])

    def test_revision_preflight_data_shortage_is_not_scheduler_block(self):
        policy = runtime_failure_policy(
            stage="revision_preflight",
            error_code="REVISION_BASELINE_MISSING",
            retryable=False,
        )
        self.assertEqual(policy["run_status"], "PRECHECK_NOT_READY")
        self.assertEqual(policy["next_action"], "COMPLETE_RUN_AND_KEEP_NEXT_SLOT")
        self.assertFalse(policy["automation_state_mutation_allowed"])
        self.assertFalse(policy["self_disable_allowed"])
        self.assertFalse(policy["self_pause_allowed"])
        self.assertFalse(policy["scheduler_terminal"])
        self.assertTrue(policy["automation_continues"])
        self.assertTrue(policy["preserve_enabled_state"])

    def test_snapshot_building_is_not_scheduler_block(self):
        policy = runtime_failure_policy(
            stage="production_preflight",
            error_code="SNAPSHOT_BUILDING",
            retryable=False,
        )
        self.assertEqual(policy["run_status"], "PRECHECK_NOT_READY")
        self.assertTrue(policy["automation_continues"])
        self.assertFalse(policy["automation_state_mutation_allowed"])

    def test_wrong_id_fails_closed(self):
        state = self.state(False)
        state["id"] = "wrong"
        with self.assertRaises(AutomationStateGuardError):
            classify_pause(state, observed_at="2026-09-07T01:01:48.674172Z")

    def test_invalid_prior_pause_count_fails_closed(self):
        with self.assertRaises(AutomationStateGuardError):
            classify_pause(
                self.state(False),
                observed_at="2026-09-07T01:01:48.674172Z",
                prior_pause_count=-1,
            )


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
from __future__ import annotations

import unittest

from instagram_tcg_content.automation_state_guard import (
    AutomationStateGuardError,
    CANONICAL_ID,
    CANONICAL_TITLE,
    classify_pause,
    runtime_failure_policy,
    snapshot_state,
)


class AutomationPauseRecoveryV30Tests(unittest.TestCase):
    def state(self, enabled: bool = False) -> dict:
        return {
            "id": CANONICAL_ID,
            "title": CANONICAL_TITLE,
            "is_enabled": enabled,
            "schedule": "RRULE:FREQ=HOURLY;BYMINUTE=0;BYSECOND=0",
            "timing_mode": "exact_schedule",
            "prompt": "stable",
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
        self.assertEqual(result["priority"], "HIGH")

    def test_third_pause_escalates_critical_priority(self):
        result = classify_pause(
            self.state(False),
            observed_at="2026-09-07T01:01:48.674172Z",
            prior_pause_count=2,
        )
        self.assertEqual(result["recurrence_count"], 3)
        self.assertEqual(result["event_class"], "PAUSE_RECURRENCE_CRITICAL")
        self.assertEqual(result["priority"], "CRITICAL")

    def test_schedule_start_disable_without_run_is_fingerprinted_not_attributed(self):
        state = self.state(False)
        state["updated_at"] = "2026-09-08T01:07:01.377102Z"
        state["last_run_time"] = "2026-09-07T20:00:56.644698Z"
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
        self.assertEqual(result["schedule_start_slot_kst"], "2026-09-08T10:00+09:00")
        self.assertFalse(result["state_transition_is_root_cause"])
        self.assertEqual(result["cause_status"], "unresolved")
        self.assertEqual(result["cause_class"], "CONTROL_PLANE_ATTRIBUTION_UNAVAILABLE")
        self.assertEqual(result["recurrence_count"], 3)
        self.assertEqual(result["priority"], "CRITICAL")

    def test_missed_slots_anchor_to_last_run_not_disable_time(self):
        state = self.state(False)
        state["updated_at"] = "2026-09-08T01:07:01.377102Z"
        state["last_run_time"] = "2026-09-07T20:00:56.644698Z"
        result = classify_pause(
            state,
            observed_at="2026-09-08T05:44:00Z",
            prior_pause_count=2,
        )
        self.assertEqual(result["missed_slot_anchor"], "last_run_plus_early_grace")
        self.assertEqual(result["schedule_run_early_grace_minutes"], 5)
        self.assertIn("2026-09-08T06:00+09:00", result["missed_slots_kst"])
        self.assertIn("2026-09-08T10:00+09:00", result["missed_slots_kst"])
        self.assertNotIn("2026-09-08T05:00+09:00", result["missed_slots_kst"])
        self.assertFalse(result["missed_weekly_production"])
        self.assertFalse(result["missed_full_0630"])
        self.assertEqual(result["catchup_policy"], "NONE")

    def test_enabled_task_can_still_have_schedule_gap_active(self):
        state = self.state(True)
        state["updated_at"] = "2026-09-09T01:41:51.738851Z"
        state["last_run_time"] = "2026-09-08T23:31:43.768364Z"
        result = classify_pause(
            state,
            observed_at="2026-09-09T02:45:00Z",
        )
        self.assertFalse(result["pause_detected"])
        self.assertTrue(result["schedule_gap_detected"])
        self.assertTrue(result["schedule_gap_active"])
        self.assertEqual(result["event_class"], "SCHEDULE_GAP_ACTIVE")
        self.assertGreaterEqual(result["missed_slot_count"], 1)
        self.assertEqual(result["required_action"], "MONITOR_NEXT_SLOT_NO_DUPLICATE_CATCHUP")
        self.assertFalse(result["duplicate_catchup_allowed"])

    def test_snapshot_fingerprints_and_changed_fields_preserve_incident_before_state(self):
        before = self.state(False)
        previous = snapshot_state(
            before,
            observed_at="2026-09-09T01:35:52.289137Z",
        )
        after = self.state(True)
        after["updated_at"] = "2026-09-09T01:41:51.738851Z"
        result = classify_pause(
            after,
            observed_at="2026-09-09T01:42:00Z",
            previous_snapshot=previous,
        )
        self.assertEqual(result["changed_fields"], ["is_enabled"])
        self.assertFalse(result["baseline_match"])
        self.assertEqual(result["change_window_start"], previous["snapshot_observed_at"])
        self.assertIsNotNone(result["snapshot"]["fingerprints"]["schedule"])
        self.assertIsNotNone(result["snapshot"]["fingerprints"]["prompt"])

    def test_post_recovery_disable_is_recovery_regression(self):
        post_recovery = snapshot_state(
            self.state(True),
            observed_at="2026-09-09T01:42:00Z",
        )
        recurrent = self.state(False)
        recurrent["updated_at"] = "2026-09-09T01:50:00Z"
        result = classify_pause(
            recurrent,
            observed_at="2026-09-09T01:51:00Z",
            prior_pause_count=1,
            post_recovery_snapshot=post_recovery,
        )
        self.assertEqual(result["event_class"], "RECOVERY_REGRESSION")
        self.assertFalse(result["post_recovery_match"])

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

    def test_missed_weekly_production_requests_user_recovery_only(self):
        state = self.state(False)
        state["last_run_time"] = "2026-09-14T08:00:10Z"
        state["updated_at"] = "2026-09-14T10:07:01Z"
        result = classify_pause(
            state,
            observed_at="2026-09-14T11:05:00Z",
        )
        self.assertTrue(result["missed_weekly_production"])
        self.assertIn("2026-09-14T19:00+09:00", result["missed_slots_kst"])
        self.assertEqual(result["catchup_policy"], "USER_REQUESTED_RECOVERY_ONLY")
        self.assertFalse(result["duplicate_catchup_allowed"])

    def test_enabled_state_is_not_pause_incident(self):
        state = self.state(True)
        state["last_run_time"] = "2026-09-07T00:30:10Z"
        result = classify_pause(
            state,
            observed_at="2026-09-07T00:31:00Z",
        )
        self.assertFalse(result["pause_detected"])
        self.assertEqual(result["required_action"], "NONE")
        self.assertTrue(result["desired_enabled_state"])
        self.assertEqual(result["event_class"], "NONE")

    def test_title_drift_is_captured_instead_of_aborting_snapshot(self):
        baseline = self.state(True)
        baseline["updated_at"] = "2026-09-09T01:35:00Z"
        baseline["last_run_time"] = "2026-09-09T01:30:10Z"
        previous = snapshot_state(
            baseline,
            observed_at="2026-09-09T01:40:00Z",
        )
        drifted = dict(baseline)
        drifted["title"] = "인스타 카드정보 변경됨"
        drifted["updated_at"] = "2026-09-09T01:41:00Z"
        result = classify_pause(
            drifted,
            observed_at="2026-09-09T01:42:00Z",
            previous_snapshot=previous,
        )
        self.assertFalse(result["title_matches_canonical"])
        self.assertEqual(result["changed_fields"], ["title"])
        self.assertEqual(result["control_plane_drift_fields"], ["title"])
        self.assertEqual(result["event_class"], "CONTROL_PLANE_DRIFT")
        self.assertEqual(result["required_action"], "REVIEW_VERIFIED_CONTROL_PLANE_DRIFT")
        self.assertEqual(result["cause_class"], "CONTROL_PLANE_ATTRIBUTION_UNAVAILABLE")
        self.assertEqual(result["final_root_cause_class"], "UNRESOLVED_CONTROL_PLANE")


    def test_first_snapshot_wrong_schedule_is_control_plane_drift(self):
        state = self.state(True)
        state["schedule"] = "RRULE:FREQ=HOURLY;BYMINUTE=30;BYSECOND=0"
        state["last_run_time"] = "2026-09-09T01:00:10Z"
        result = classify_pause(state, observed_at="2026-09-09T01:01:00Z")
        self.assertIn("schedule", result["control_plane_drift_fields"])
        self.assertEqual(result["event_class"], "CONTROL_PLANE_DRIFT")
        self.assertEqual(result["required_action"], "REVIEW_VERIFIED_CONTROL_PLANE_DRIFT")

    def test_empty_title_still_fails_closed(self):
        state = self.state(True)
        state["title"] = ""
        with self.assertRaises(AutomationStateGuardError):
            snapshot_state(state, observed_at="2026-09-09T01:42:00Z")

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

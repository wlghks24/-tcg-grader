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

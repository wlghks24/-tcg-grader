#!/usr/bin/env python3
import unittest

from instagram_tcg_content.production_state import (
    can_start_user_requested_recovery,
    empty_state,
    record_catchup_attempt,
)


class MissedSlotRecoveryV346Tests(unittest.TestCase):
    def test_silent_gap_requires_independent_missed_slot_evidence(self):
        state = empty_state()
        allowed, reason = can_start_user_requested_recovery(
            state, "2026-09-28", user_requested=True
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, "NO_BLOCKED_BASELINE_EVIDENCE")

    def test_evidence_does_not_replace_explicit_user_request(self):
        state = empty_state()
        allowed, reason = can_start_user_requested_recovery(
            state,
            "2026-09-28",
            user_requested=False,
            missed_scheduled_slot_evidence=True,
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, "USER_REQUEST_REQUIRED")

    def test_evidence_allows_one_bounded_recovery_without_fake_blocked_record(self):
        state = empty_state()
        allowed, reason = can_start_user_requested_recovery(
            state,
            "2026-09-28",
            user_requested=True,
            missed_scheduled_slot_evidence=True,
        )
        self.assertTrue(allowed)
        self.assertEqual(
            reason, "USER_REQUESTED_RECOVERY_ALLOWED_WITH_MISSED_SLOT_EVIDENCE"
        )
        self.assertNotIn("2026-09-28", state["blocked_attempts"])

        record_catchup_attempt(state, "2026-09-28")
        allowed, reason = can_start_user_requested_recovery(
            state,
            "2026-09-28",
            user_requested=True,
            missed_scheduled_slot_evidence=True,
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, "CATCHUP_BUDGET_EXHAUSTED")


if __name__ == "__main__":
    unittest.main()

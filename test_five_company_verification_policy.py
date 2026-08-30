#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression checks for the five-company official slab verification policy."""

import unittest
from collections import Counter
from unittest import mock
from urllib.error import HTTPError

import grading_cert_verifier
import slab_verification_batch


class FiveCompanyVerificationPolicyTests(unittest.TestCase):
    def test_all_five_graders_have_official_lookup_configuration(self):
        expected = {"PSA", "BGS", "CGC", "TAG", "BRG"}
        self.assertTrue(expected.issubset(set(grading_cert_verifier.OFFICIAL)))
        for company in expected:
            cfg = grading_cert_verifier.OFFICIAL[company]
            self.assertTrue(cfg.get("home"))
            self.assertTrue(cfg.get("direct"))
            self.assertTrue(cfg.get("hosts"))

    def test_same_hard_safety_policy_applies_to_every_company(self):
        self.assertEqual(slab_verification_batch.MAX_LOOKUPS_PER_COMPANY, 2)
        self.assertGreaterEqual(slab_verification_batch.MIN_DELAY_SECONDS, 60.0)
        self.assertIn(403, slab_verification_batch.IMMEDIATE_BLOCK_HTTP_STATUSES)
        self.assertIn(429, slab_verification_batch.IMMEDIATE_BLOCK_HTTP_STATUSES)

    def _assert_block_is_never_retried(self, status):
        error = HTTPError(
            "https://www.psacard.com/cert/123456/psa",
            status,
            "blocked",
            {},
            None,
        )
        with mock.patch.object(grading_cert_verifier, "_request", side_effect=error) as request_mock:
            with mock.patch.object(grading_cert_verifier.time, "sleep") as sleep_mock:
                with self.assertRaises(HTTPError):
                    grading_cert_verifier._fetch("PSA", "https://www.psacard.com/cert/123456/psa", retries=3)
        self.assertEqual(request_mock.call_count, 1)
        sleep_mock.assert_not_called()

    def test_429_is_never_retried_inside_verifier(self):
        self._assert_block_is_never_retried(429)

    def test_403_is_never_retried_inside_verifier(self):
        self._assert_block_is_never_retried(403)

    def test_block_runs_local_self_audit_and_active_cooldown(self):
        cooldowns = {}
        cooldown = slab_verification_batch.set_cooldown(
            cooldowns,
            "TAG",
            {"http_status": 429, "recommended_cooldown_seconds": 1800},
            strike_count=1,
        )
        audit = slab_verification_batch.build_block_self_audit(
            "TAG",
            429,
            cooldown,
            60.0,
        )
        self.assertTrue(audit["passed"])
        self.assertEqual(audit["action"], "local_policy_audit_only_no_network_retry")
        self.assertTrue(audit["checks"]["network_retry_for_block_is_suppressed"])

    def test_repeated_blocks_increase_cooldown(self):
        first = slab_verification_batch.set_cooldown(
            {},
            "PSA",
            {"http_status": 429, "recommended_cooldown_seconds": 1800},
            strike_count=1,
        )
        second = slab_verification_batch.set_cooldown(
            {},
            "PSA",
            {"http_status": 429, "recommended_cooldown_seconds": 1800},
            strike_count=2,
        )
        self.assertEqual(first["seconds"], 1800)
        self.assertEqual(second["seconds"], 3600)
        self.assertEqual(second["backoff_multiplier"], 2)

    def test_403_recovery_plan_recommends_manual_after_repeat(self):
        result = {
            "http_status": 403,
            "retry_after_seconds": None,
            "recovery": {
                "block_kind": "access_control",
                "manual_verification_url": "https://www.beckett.com/grading/card-lookup",
            },
        }
        cooldown = {"until": "2099-01-01T00:00:00Z", "seconds": 14400}
        plan = slab_verification_batch.build_recovery_plan("BGS", 403, result, cooldown, 2)
        self.assertEqual(plan["action"], "manual_official_lookup_recommended_after_cooldown")
        self.assertTrue(plan["do_not_bypass_access_controls"])

    def test_idle_pacing_skips_when_only_blocked_company_remains(self):
        candidates = [
            {"company": "PSA", "certification_id": "111111"},
            {"company": "PSA", "certification_id": "222222"},
        ]
        runnable = slab_verification_batch.has_future_runnable_candidate(
            candidates,
            1,
            2,
            1,
            {"PSA"},
            Counter({"PSA": 1}),
            {},
        )
        self.assertFalse(runnable)

    def test_idle_pacing_waits_when_other_company_can_run(self):
        candidates = [
            {"company": "PSA", "certification_id": "111111"},
            {"company": "CGC", "certification_id": "222222"},
        ]
        runnable = slab_verification_batch.has_future_runnable_candidate(
            candidates,
            1,
            2,
            1,
            {"PSA"},
            Counter({"PSA": 1}),
            {},
        )
        self.assertTrue(runnable)


if __name__ == "__main__":
    unittest.main()

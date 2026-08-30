#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression checks for the five-company official slab verification policy."""

import unittest
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

    def test_429_is_never_retried_inside_verifier(self):
        error = HTTPError(
            "https://www.psacard.com/cert/123456/psa",
            429,
            "Too Many Requests",
            {},
            None,
        )
        with mock.patch.object(grading_cert_verifier, "_request", side_effect=error) as request_mock:
            with mock.patch.object(grading_cert_verifier.time, "sleep") as sleep_mock:
                with self.assertRaises(HTTPError):
                    grading_cert_verifier._fetch("PSA", "https://www.psacard.com/cert/123456/psa", retries=3)
        self.assertEqual(request_mock.call_count, 1)
        sleep_mock.assert_not_called()

    def test_block_runs_local_self_audit_and_active_cooldown(self):
        cooldowns = {}
        cooldown = slab_verification_batch.set_cooldown(
            cooldowns,
            "TAG",
            {"http_status": 429, "recommended_cooldown_seconds": 1800},
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


if __name__ == "__main__":
    unittest.main()

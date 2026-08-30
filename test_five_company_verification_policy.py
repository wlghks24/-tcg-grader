#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression checks for the five-company official slab verification policy."""

import unittest

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
        # slab_verification_batch applies these constants generically per company,
        # so TAG/BRG receive the exact same policy as PSA/BGS/CGC once candidates exist.
        self.assertEqual(slab_verification_batch.MAX_LOOKUPS_PER_COMPANY, 2)
        self.assertGreaterEqual(slab_verification_batch.MIN_DELAY_SECONDS, 60.0)
        self.assertIn(403, slab_verification_batch.IMMEDIATE_BLOCK_HTTP_STATUSES)
        self.assertIn(429, slab_verification_batch.IMMEDIATE_BLOCK_HTTP_STATUSES)


if __name__ == "__main__":
    unittest.main()

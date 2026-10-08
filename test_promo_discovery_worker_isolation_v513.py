#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression: a broken official index must not erase unrelated discoveries."""
import concurrent.futures
import unittest
import update_promo_events as promo


def ready(value=None, error=None):
    future = concurrent.futures.Future()
    if error is None:
        future.set_result(value)
    else:
        future.set_exception(error)
    return future


class PromoDiscoveryWorkerIsolationV513(unittest.TestCase):
    def setUp(self):
        self.indexes = (
            ("KR", "포켓몬 카드", "https://pokemoncard.co.kr/main"),
            ("JP", "원피스 카드", "https://www.onepiece-cardgame.com/events/"),
        )

    def test_one_crash_keeps_other_sources_and_reports_failure(self):
        verified = [{"game": "포켓몬 카드", "region": "KR", "source": "https://pokemoncard.co.kr/main"}]
        result = promo._resolved_discovery_results(
            self.indexes,
            [ready((verified, [])), ready(error=RuntimeError("probe-fault"))],
        )
        self.assertEqual(result[0], (verified, []))
        self.assertEqual(result[1][0], [])
        self.assertEqual(len(result[1][1]), 1)
        self.assertIn("JP 원피스 카드", result[1][1][0])
        self.assertIn("RuntimeError", result[1][1][0])

    def test_malformed_worker_data_is_an_explicit_error(self):
        for malformed in (None, ("not-a-list", []), ([], "not-a-list"), ([], [None])):
            with self.subTest(malformed=malformed):
                rows = promo._resolved_discovery_results(self.indexes[:1], [ready(malformed)])
                self.assertEqual(rows[0][0], [])
                self.assertEqual(len(rows[0][1]), 1)

    def test_worker_count_mismatch_is_a_hard_error(self):
        with self.assertRaises(ValueError):
            promo._resolved_discovery_results(self.indexes, [ready(([], []))])

    def test_process_interrupt_is_not_suppressed(self):
        with self.assertRaises(KeyboardInterrupt):
            promo._resolved_discovery_results(
                self.indexes[:1], [ready(error=KeyboardInterrupt("interrupt"))]
            )


if __name__ == "__main__":
    unittest.main()

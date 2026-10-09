#!/usr/bin/env python3
"""V562: purchase-source probe singleflight does not hide source failures."""
import unittest
from unittest import mock

import update_purchase_sources as purchase


class PurchaseProbeSingleflightV562(unittest.TestCase):
    def test_exact_same_url_reuses_probe_but_keeps_each_source_status(self):
        sources = [
            {"name": "포켓몬 상품", "url": "https://pokemonkorea.co.kr/"},
            {"name": "나루토 공식", "url": "https://www.naruto-cardgame.com/asia-en/"},
            {"name": "포켓몬 판매처", "url": "https://pokemonkorea.co.kr/"},
            {"name": "나루토 해외", "url": "https://www.naruto-cardgame.com/asia-en/"},
            {"name": "독립 원피스", "url": "https://en.onepiece-cardgame.com/products/"},
        ]
        calls = []
        def fake_probe(row):
            calls.append(row["url"])
            if row["url"].startswith("https://pokemonkorea"):
                return row["name"], "재확인 필요·기존 주소 유지 (HTTPError: status 410)"
            return row["name"], "정상"
        with mock.patch.object(purchase, "probe", side_effect=fake_probe):
            statuses, errors = purchase.probe_official_sources(sources)
        self.assertEqual(3, len(calls), "same exact URL is probed only once")
        self.assertEqual(3, len(set(calls)))
        self.assertEqual(set(statuses), {x["name"] for x in sources})
        self.assertEqual(statuses["포켓몬 상품"], statuses["포켓몬 판매처"])
        self.assertEqual(len(errors), 2, "one failed URL reports both affected names")
        self.assertTrue(any(x.startswith("포켓몬 상품:") for x in errors))
        self.assertTrue(any(x.startswith("포켓몬 판매처:") for x in errors))

    def test_distinct_paths_are_not_conflated_and_access_block_is_preserved(self):
        sources = [
            {"name": "official homepage", "url": "https://pokemoncard.co.kr/main"},
            {"name": "product detail", "url": "https://pokemoncard.co.kr/card/225"},
            {"name": "blocked", "url": "https://www.psacard.com/services/tradingcardgrading"},
        ]
        def fake_probe(row):
            if row["name"] == "blocked":
                return row["name"], "접속 제한·기존 주소 유지 (HTTP 403)"
            if row["name"] == "product detail":
                return row["name"], "재확인 필요·기존 주소 유지 (HTTPError: status 410)"
            return row["name"], "정상"
        with mock.patch.object(purchase, "probe", side_effect=fake_probe) as probe:
            statuses, errors = purchase.probe_official_sources(sources)
        self.assertEqual(probe.call_count, 3)
        self.assertEqual(statuses["official homepage"], "정상")
        self.assertIn("410", statuses["product detail"])
        self.assertIn("403", statuses["blocked"])
        self.assertEqual(len(errors), 1, "preserve existing 403 classification")
        self.assertTrue(errors[0].startswith("product detail:"))

    def test_each_cycle_reprobes_and_exceptions_fail_closed(self):
        rows = [{"name": "A", "url": "https://pokemoncard.co.kr/main"},
                {"name": "B", "url": "https://pokemoncard.co.kr/main"}]
        with mock.patch.object(purchase, "probe", return_value=("A", "정상")) as probe:
            self.assertEqual(purchase.probe_official_sources(rows)[0]["B"], "정상")
            self.assertEqual(purchase.probe_official_sources(rows)[0]["B"], "정상")
            self.assertEqual(probe.call_count, 2, "no cross-cycle cached status")
        with mock.patch.object(purchase, "probe", side_effect=TimeoutError("source unavailable")):
            with self.assertRaises(TimeoutError):
                purchase.probe_official_sources(rows)

    def test_empty_targets_performs_no_request(self):
        with mock.patch.object(purchase, "probe") as probe:
            self.assertEqual(purchase.probe_official_sources([]), ({}, []))
        probe.assert_not_called()


if __name__ == "__main__":
    unittest.main()

"""Offline V675 tests: malformed anchors cannot discard valid official leads."""
from __future__ import annotations

import datetime as dt
from email.message import Message
from urllib.error import HTTPError
import unittest
from unittest.mock import patch

from tcg_reliability import china_official_catalog_v571 as legacy
from tcg_reliability import china_official_catalog_v675 as shadow

CN, HK, TW = (item[2] for item in legacy.SOURCES)
CN_FIRST = (
    '<a href="/tcg/product/23939.html">'
    '\u793c\u76d2\u7ec4\u5408 Product 2026-09-21</a>'
)
CN_SECOND = (
    '<a href="/tcg/product/23940.html">'
    '\u6536\u85cf\u76d2 Product 2026-09-22</a>'
)
CN_BAD = (
    '<a href="https://[broken">'
    '\u793c\u76d2 Product 2026-09-23</a>'
)
HK_BOX = '<li>30th CELEBRATION SPECIAL BOX<a href="/hk/archives/8939/">\u5546\u54c1\u8cc7\u8a0a</a></li>'
TW_BOX = '<li>SPECIAL BOX TAIWAN<a href="/tw/archives/9283/">\u5546\u54c1\u8cc7\u8a0a</a></li>'


def fixtures(url: str) -> str:
    return CN_FIRST + CN_BAD + CN_SECOND if "pokemon.cn" in url else (
        HK_BOX if "/hk/" in url else TW_BOX
    )


class ChinaV675IsolationTests(unittest.TestCase):
    def test_reproduced_legacy_breakage_and_two_valid_cn_links_survive(self):
        body = CN_FIRST + CN_BAD + CN_SECOND
        with self.assertRaises(ValueError):
            legacy.parse_official_html(body, "CN-S", "CN", CN, "review")
        rows = shadow.parse_official_html(body, "CN-S", "CN", CN, "review")
        self.assertEqual(2, len(rows))
        self.assertEqual(
            {CN + "/23939.html", CN + "/23940.html"},
            {row["source"] for row in rows},
        )

    def test_shields_malformed_relative_ipv6_and_keeps_valid_links(self):
        for href in ("https://[bad", "//[bad/path", "https://[::zz/"):
            with self.subTest(href=href):
                body = CN_FIRST + '<a href="' + href + '">BOX</a>' + CN_SECOND
                rows = shadow.parse_official_html(body, "CN-S", "CN", CN, "review")
                self.assertEqual(2, len(rows))

    def test_unmodified_legacy_candidate_decisions_on_clean_html(self):
        for edition, locale, url, body in (
            ("CN-S", "CN", CN, CN_FIRST + CN_SECOND),
            ("CN-T", "HK", HK, HK_BOX),
            ("CN-T", "TW", TW, TW_BOX),
        ):
            with self.subTest(locale=locale):
                self.assertEqual(
                    legacy.parse_official_html(body, edition, locale, url, "review"),
                    shadow.parse_official_html(body, edition, locale, url, "review"),
                )

    def test_multi_node_hk_tw_product_context_is_not_concatenated(self):
        for edition, locale, index, detail in (
            ("CN-T", "HK", HK, "/hk/archives/8939/"),
            ("CN-T", "TW", TW, "/tw/archives/9283/"),
        ):
            with self.subTest(locale=locale):
                body = (
                    "<div>OLD NAVIGATION SECTION</div>"
                    "<div>NEW COLLECTOR SPECIAL BOX</div>"
                    '<a href="' + detail + '">\u5546\u54c1\u8cc7\u8a0a</a>'
                )
                previous = legacy.parse_official_html(
                    body, edition, locale, index, "review"
                )
                current = shadow.parse_official_html(
                    body, edition, locale, index, "review"
                )
                self.assertEqual(previous, current)
                self.assertEqual("NEW COLLECTOR SPECIAL BOX", current[0]["name"])

    def test_host_and_edition_locale_boundary(self):
        for href in (
            "https://evil.example/tcg/product/12345.html",
            "/tcg/product/12345.html?trace=1",
            "http://www.pokemon.cn/tcg/product/12345.html",
            "//[bad/path",
            "https://user@www.pokemon.cn/tcg/product/12345.html",
            "/tcg/product/1.html",
            "https://www.pokemon.cn/tcg/product/12345.html#card",
            "/tcg/product/12345.html\n",
        ):
            with self.subTest(href=href):
                self.assertIsNone(shadow.safe_link(CN, href, "CN-S"))
        self.assertIsNone(shadow.safe_link(HK, "/tw/archives/9283/", "CN-T"))
        self.assertIsNone(shadow.safe_link(TW, "/hk/archives/8939/", "CN-T"))
        self.assertEqual([], shadow.parse_official_html(
            TW_BOX, "CN-T", "HK", HK, "review"))
        self.assertEqual([], shadow.parse_official_html(
            CN_FIRST, "CN-S", "HK", CN, "review"))

    def test_unverified_product_and_price_never_promoted(self):
        rows = shadow.fetch_official_products(fetcher=fixtures)
        self.assertEqual([], rows["errors"])
        self.assertEqual(4, len(rows["items"]))
        self.assertFalse(rows["prices_verified"])
        self.assertFalse(rows["holdings_created"])
        for row in rows["items"]:
            self.assertEqual("BOX", row["asset"])
            self.assertIs(row["market_eligible"], False)
            self.assertEqual("NONE", row["price_evidence"])
            self.assertEqual("HOLD", row["market_decision"])
            self.assertIsNone(row["investment_score"])
            self.assertEqual("official_catalog", row["source_grade"])
        self.assertEqual({"CN", "HK", "TW"}, {x["locale"] for x in rows["coverage"]})

    def test_source_failure_isolated_while_other_locales_survive(self):
        def fetch(url):
            if "/hk/" in url:
                raise TimeoutError("private details must not leave device")
            return fixtures(url)
        result = shadow.fetch_official_products(fetcher=fetch)
        self.assertEqual(
            [{"region": "CN-T", "locale": "HK", "error": "TimeoutError"}],
            result["errors"],
        )
        self.assertEqual({"CN", "TW"}, {x["market_locale"] for x in result["items"]})
        self.assertNotIn("private details", str(result))

    def test_long_server_retry_after_never_shortened(self):
        calls = []
        def fetch(url):
            calls.append(url)
            if url == CN:
                headers = Message()
                headers["Retry-After"] = "3600"
                raise HTTPError(url, 429, "too many", headers, None)
            return fixtures(url)
        result = shadow.fetch_official_products(fetcher=fetch)
        self.assertEqual(1, calls.count(CN))
        self.assertEqual(
            [{"region": "CN-S", "locale": "CN", "error": "HTTPError"}],
            result["errors"],
        )
        self.assertEqual({"HK", "TW"}, {x["market_locale"] for x in result["items"]})

    def test_oversized_and_invalid_html_or_source_rejected(self):
        self.assertEqual([], shadow.parse_official_html(
            "A" * (legacy.MAX_BYTES + 1), "CN-S", "CN", CN, "review"))
        self.assertEqual([], shadow.parse_official_html(
            None, "CN-S", "CN", CN, "review"))
        self.assertEqual([], shadow.parse_official_html(
            CN_FIRST, "CN-T", "CN", CN, "review"))
        self.assertEqual([], shadow.parse_official_html(
            CN_FIRST, "CN-S", "CN", "https://not-official.example/", "review"))

    def test_limits_and_duplicate_sources_preserved(self):
        body = CN_FIRST * 3 + "".join(
            '<a href="/tcg/product/' + str(i) + '.html">'
            '\u793c\u76d2 Product 2026-09-21</a>'
            for i in range(30000, 30060)
        )
        rows = shadow.parse_official_html(body, "CN-S", "CN", CN, "review")
        self.assertEqual(legacy.MAX_ROWS_PER_SOURCE, len(rows))
        self.assertEqual(len(rows), len({x["source"] for x in rows}))

    def test_offline_fetcher_never_invokes_network(self):
        with patch.object(shadow, "_network", side_effect=AssertionError("network")):
            result = shadow.fetch_official_products(
                fetcher=fixtures, now=dt.datetime(
                    2026, 10, 26, tzinfo=dt.timezone.utc,
                )
            )
        self.assertTrue(result["items"])
        self.assertEqual("2026-10-26T00:00:00+00:00", result["checked_at"])


if __name__ == "__main__":
    unittest.main()

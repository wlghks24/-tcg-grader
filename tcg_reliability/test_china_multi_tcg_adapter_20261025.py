"""Offline contract tests for multi-TCG China catalog adapters."""
import unittest

from tcg_reliability.china_multi_tcg_adapter_20261025 import (
    OfficialCatalogSource, catalog_candidate, validate_source, validate_sources, official_watch_targets, display_region, catalog_identity, group_catalog_by_game,
)


class MultiTcgAdapterTests(unittest.TestCase):
    def source(self, game="One Piece", edition="CN-T", locale="HK", url="https://official.example/catalog/"):
        return OfficialCatalogSource(game, edition, locale, url, r"^/products/[0-9]+/$", "verified_20261025")

    def test_multiple_games_are_supported_as_review_only(self):
        for game in ("One Piece", "Naruto", "Pokémon"):
            with self.subTest(game=game):
                source = self.source(game=game)
                self.assertTrue(validate_source(source, verified_hosts=frozenset({"official.example"})))
                row = catalog_candidate(source, title="商品示例", detail_url="https://official.example/products/123/", checked_at="2026-10-25T00:00:00Z", verified_hosts=frozenset({"official.example"}))
                self.assertEqual(row["game"], game)
                self.assertEqual(row["market_decision"], "HOLD")
                self.assertEqual(row["asset"], "UNVERIFIED_PRODUCT")
                self.assertFalse(row["market_eligible"])

    def test_candidate_requires_independent_host_approval(self):
        source = self.source()
        kwargs = {"title": "商品示例", "detail_url": "https://official.example/products/123/", "checked_at": "now"}
        self.assertIsNone(catalog_candidate(source, **kwargs))
        self.assertIsNone(catalog_candidate(source, **kwargs, verified_hosts=frozenset({"evil.example"})))
        self.assertIsNotNone(catalog_candidate(source, **kwargs, verified_hosts=frozenset({"official.example"})))

    def test_candidate_rejects_invalid_observation_timestamp(self):
        source = self.source()
        for stamp in ("", None, "x" * 81):
            with self.subTest(stamp=stamp):
                self.assertIsNone(catalog_candidate(source, title="商品示例",
                    detail_url="https://official.example/products/123/", checked_at=stamp,
                    verified_hosts=frozenset({"official.example"})))

    def test_rejects_mismatched_edition_locale(self):
        self.assertFalse(validate_source(self.source(edition="CN-S", locale="HK"), verified_hosts=frozenset({"official.example"})))

    def test_rejects_unverified_hosts(self):
        self.assertFalse(validate_source(self.source(), verified_hosts=frozenset({"other.example"})))

    def test_rejects_external_detail_link(self):
        self.assertIsNone(catalog_candidate(self.source(), title="商品示例", detail_url="https://evil.example/products/123/", checked_at="now"))

    def test_rejects_duplicate_sources(self):
        self.assertFalse(validate_sources([self.source(), self.source()], verified_hosts=frozenset({"official.example"})))

    def test_official_watch_sources_are_not_product_parsers(self):
        sources = official_watch_targets()
        self.assertEqual(len(sources), 6)
        self.assertEqual({s['game'] for s in sources}, {'One Piece', 'Naruto'})
        self.assertTrue(all(s['state'] == 'watch_only' for s in sources))
        self.assertEqual({s['locale'] for s in sources}, {'CN', 'HK', 'TW'})
        self.assertTrue(all(s['url'].startswith('https://') for s in sources))

    def test_unified_cn_tab_preserves_game_and_locale(self):
        rows = []
        for game in ("Pokémon", "One Piece", "Naruto"):
            for region, locale in (("CN-S", "CN"), ("CN-T", "HK"), ("CN-T", "TW")):
                rows.append({"game": game, "region": region, "market_locale": locale,
                             "source": f"https://official.example/{game}/{locale}/1"})
        result = group_catalog_by_game(rows + rows)
        for game in ("Pokémon", "One Piece", "Naruto"):
            self.assertEqual(len(result[game]["CN"]), 3)
            self.assertEqual(len(result[game]["ALL"]), 3)
            self.assertEqual(len(result[game]["KR"]), 0)
            self.assertEqual({r["market_locale"] for r in result[game]["CN"]}, {"CN", "HK", "TW"})
        self.assertEqual(display_region("CN-S"), "CN")
        self.assertEqual(display_region("CN-T"), "CN")
        self.assertEqual(display_region("JP"), "JP")
        self.assertIsNone(display_region("ASIA"))

    def test_rejects_cross_game_and_invalid_edition_identity(self):
        self.assertIsNone(catalog_identity({"game": "Other", "region": "CN-T",
                                            "market_locale": "HK", "source": "https://official.example/x"}))
        self.assertIsNone(catalog_identity({"game": "Naruto", "region": "CN-S",
                                            "market_locale": "TW", "source": "https://official.example/x"}))

    def test_catalog_identity_rejects_credentials_query_and_malformed_ports(self):
        base = {"game": "One Piece", "region": "CN-T", "market_locale": "HK"}
        for url in ("https://user:pass@official.example/products/1",
                    "https://official.example/products/1?token=secret",
                    "https://official.example:invalid/products/1",
                    "https://official.example/products/1#fragment"):
            with self.subTest(url=url):
                self.assertIsNone(catalog_identity({**base, "source": url}))

    def test_candidate_rejects_credentials_and_invalid_port(self):
        source = self.source()
        for url in ("https://user:pass@official.example/products/123/",
                    "https://official.example:invalid/products/123/"):
            self.assertIsNone(catalog_candidate(source, title="商品示例", detail_url=url, checked_at="now"))

    def test_rejects_complex_regex_and_non_path_regex(self):
        for pattern in (r"^(a+)+$", r"^/products/(?=secret)[0-9]+/$",
                        r"^https://official.example/products/[0-9]+/$",
                        r"^/products/.*$", r"^/products/[0-9]{100000}/$"):
            source = OfficialCatalogSource("One Piece", "CN-T", "HK",
                                           "https://official.example/catalog/", pattern, "verified_20261025")
            self.assertFalse(validate_source(source, verified_hosts=frozenset({"official.example"})))

    def test_rejects_unknown_game(self):
        self.assertFalse(validate_source(self.source(game="Unknown"), verified_hosts=frozenset({"official.example"})))


if __name__ == "__main__":
    unittest.main()

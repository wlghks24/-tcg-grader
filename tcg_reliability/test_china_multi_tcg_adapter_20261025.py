"""Offline contract tests for multi-TCG China catalog adapters."""
import unittest

from tcg_reliability.china_multi_tcg_adapter_20261025 import (
    OfficialCatalogSource, catalog_candidate, validate_source, validate_sources,
)


class MultiTcgAdapterTests(unittest.TestCase):
    def source(self, game="One Piece", edition="CN-T", locale="HK", url="https://official.example/catalog/"):
        return OfficialCatalogSource(game, edition, locale, url, r"^/products/[0-9]+/$", "verified_20261025")

    def test_multiple_games_are_supported_as_review_only(self):
        for game in ("One Piece", "Naruto", "Pokémon"):
            with self.subTest(game=game):
                source = self.source(game=game)
                self.assertTrue(validate_source(source, verified_hosts=frozenset({"official.example"})))
                row = catalog_candidate(source, title="商品示例", detail_url="https://official.example/products/123/", checked_at="2026-10-25T00:00:00Z")
                self.assertEqual(row["game"], game)
                self.assertEqual(row["market_decision"], "HOLD")
                self.assertEqual(row["asset"], "UNVERIFIED_PRODUCT")
                self.assertFalse(row["market_eligible"])

    def test_rejects_mismatched_edition_locale(self):
        self.assertFalse(validate_source(self.source(edition="CN-S", locale="HK"), verified_hosts=frozenset({"official.example"})))

    def test_rejects_unverified_hosts(self):
        self.assertFalse(validate_source(self.source(), verified_hosts=frozenset({"other.example"})))

    def test_rejects_external_detail_link(self):
        self.assertIsNone(catalog_candidate(self.source(), title="商品示例", detail_url="https://evil.example/products/123/", checked_at="now"))

    def test_rejects_duplicate_sources(self):
        self.assertFalse(validate_sources([self.source(), self.source()], verified_hosts=frozenset({"official.example"})))

    def test_rejects_unknown_game(self):
        self.assertFalse(validate_source(self.source(game="Unknown"), verified_hosts=frozenset({"official.example"})))


if __name__ == "__main__":
    unittest.main()

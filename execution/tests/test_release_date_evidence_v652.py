"""Published news timestamps must never become verified product release dates."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import update_releases as releases


class ReleaseDateEvidenceTests(unittest.TestCase):
    def test_publication_timestamps_and_nearby_release_headings_are_not_dates(self):
        for text in (
            "Announcements 2026-10-21T16:00:00.000Z Couture Collection Drawing FAQ",
            "Release news 2026-10-21T16:00:00.000Z Set launches November 1, 2026",
            "Published 2026-10-21. Release date November 1, 2026",
        ):
            with self.subTest(text=text):
                expected = "2026-11-01" if "November" in text else None
                self.assertEqual(expected, releases._parse_registry_date(text, require_cue=True))

    def test_explicit_release_cues_and_invalid_calendar_dates(self):
        for text in ("Release date: October 23, 2026", "Available on 2026-10-23",
                     "출시일: 2026년10월23일", "2026年10月23日(金)発売予定"):
            self.assertEqual("2026-10-23", releases._parse_registry_date(text, require_cue=True), text)
        self.assertIsNone(releases._parse_registry_date("Release date 2026-02-30", require_cue=True))

    def test_review_preserves_original_rows_without_publishing_unproven_dates(self):
        old = dict(game="Riftbound: League of Legends", region="US", name="Collection drawing FAQ",
                   release_date="2026-10-21", source="https://riftbound.leagueoflegends.com/en-us/news/a",
                   collection_method="registry_official_product_link_v478")
        original = deepcopy(old)
        accepted, review = releases.registry_date_review([old], [])
        self.assertEqual(old, original)
        self.assertEqual([], accepted)
        self.assertEqual(old["release_date"], review[0]["release_date"])
        self.assertTrue(review[0]["release_date_review_required"])
        self.assertFalse(releases.valid(old))
        self.assertEqual(review, releases.registry_date_review([old], review)[1])
        corrected = dict(old, release_date_evidence="Release date October 21, 2026")
        self.assertEqual([corrected], releases.registry_date_review([corrected], review)[0])

    def test_excerpt_retains_evidence_deep_in_product_page(self):
        text = "navigation " * 1000 + " Release date: October 23, 2026 " + "footer " * 1000
        excerpt = releases._registry_release_date_excerpt(text, "2026-10-23")
        self.assertLess(len(excerpt), 1000)
        self.assertEqual("2026-10-23", releases._parse_registry_date(excerpt, require_cue=True))

    def test_registry_fetch_requires_release_cue_and_same_official_host(self):
        source = "https://riftbound.leagueoflegends.com/en-us/"
        host = "riftbound.leagueoflegends.com"
        game = dict(id="riftbound", canonical="Riftbound: League of Legends", regions=["US"],
                    capabilities={"release":True}, official_source=source)
        index = ('<a href="/en-us/products/couture">Couture Collection Booster</a>'
                 '<a href="https://other.example/products/set">Release date October 22, 2026 Booster</a>')
        detail = '<p>Published 2026-10-21.</p><p>Release date: November 1, 2026.</p>'
        with patch.object(releases.tcg_game_registry,"load_registry",return_value={"games":[game]}), \
             patch.object(releases,"ALLOWED",{host,"other.example"}), \
             patch.object(releases,"fetch",side_effect=lambda url:index if url==source else detail) as fetch:
            rows = releases.collect_registry_releases()
        self.assertEqual(1, len(rows))
        self.assertEqual("2026-11-01", rows[0]["release_date"])
        self.assertTrue(releases._registry_release_has_date_evidence(rows[0]))
        self.assertEqual([source,source+"products/couture"], [call.args[0] for call in fetch.call_args_list])


    def test_article_titles_are_not_product_releases_even_with_dates(self):
        for name in (
            "Trading Card Game Rules and Set FAQ - Snowshade Edition",
            "Organized Play 2026-09-30T16:00:00Z Top Decks",
            "Receive a Special Promo Card at Prerelease Events!",
            "Card Search", "View More", "Others", "LIST", "Card",
        ):
            with self.subTest(name=name):
                row = dict(
                    game="Elestrals", region="US", name=name,
                    release_date="2026-10-23",
                    source="https://www.elestrals.com/news/snowshade-set-faq",
                    collection_method="registry_official_release_cue_v652",
                    release_date_evidence="Release date October 23, 2026",
                )
                self.assertFalse(releases.valid(row))

    def test_old_unverified_official_rows_are_quarantined_not_lost(self):
        from copy import deepcopy
        old = dict(
            game="Elestrals", region="US",
            name="Trading Card Game Rules and Set FAQ - Snowshade Edition",
            release_date="2026-10-05",
            source="https://www.elestrals.com/news/snowshade-set-faq",
            collection_method="registry_official_product_link_v478",
        )
        before = deepcopy(old)
        accepted, review = releases.registry_date_review([old], [])
        self.assertEqual([], accepted)
        self.assertEqual(len(review), 1)
        self.assertEqual(review[0]["source"], old["source"])
        self.assertTrue(review[0]["release_date_review_required"])
        self.assertEqual(before, old)
        self.assertFalse(releases.valid(old))

    def test_registry_collector_skips_faq_before_fetching_detail(self):
        source = "https://www.elestrals.com/"
        game = dict(id="elestrals", canonical="Elestrals", regions=["US"],
                    capabilities={"release": True}, official_source=source)
        index = (
            '<a href="/news/snowshade-set-faq">Trading Card Game Rules and Set FAQ - Snowshade Edition</a>'
            '<a href="/products/snowshade-boosters">Snowshade Booster Pack</a>'
        )
        detail = "<p>Release date October 23, 2026</p>"
        with patch.object(releases.tcg_game_registry, "load_registry", return_value={"games":[game]}), \
             patch.object(releases, "ALLOWED", {"www.elestrals.com"}), \
             patch.object(releases, "fetch", side_effect=lambda u: index if u == source else detail) as fetch:
            rows = releases.collect_registry_releases()
        self.assertEqual(1, len(rows))
        self.assertEqual("Snowshade Booster Pack", rows[0]["name"])
        fetched = [c.args[0] for c in fetch.call_args_list]
        self.assertNotIn("https://www.elestrals.com/news/snowshade-set-faq", fetched)


if __name__ == "__main__":
    unittest.main()

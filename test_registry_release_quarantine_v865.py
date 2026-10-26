"""Safety regression for legacy registry release evidence quarantine (#865).

This validates fail-closed publication inputs without writing files or networks.
The original V652 sync contract and tests remain immutable.
"""
import json
from pathlib import Path
import unittest

import update_releases


ROOT = Path(__file__).resolve().parent


class LegacyRegistryReleaseQuarantineTests(unittest.TestCase):
    def test_snapshot_counts_match_verified_lists(self):
        data = json.loads((ROOT / "releases.json").read_text(encoding="utf-8"))
        self.assertIsInstance(data.get("items"), list)
        self.assertIsInstance(data.get("archive_items"), list)
        self.assertEqual(data["current_release_count"], len(data["items"]))
        self.assertEqual(data["archive_release_count"], len(data["archive_items"]))
        self.assertEqual(data["history_count"], len(data["items"]) + len(data["archive_items"]))

    def test_unverified_legacy_rows_never_in_publishable_lists(self):
        data = json.loads((ROOT / "releases.json").read_text(encoding="utf-8"))
        for row in data["items"] + data.get("archive_items", []):
            with self.subTest(name=row.get("name", "")):
                self.assertTrue(update_releases.valid(row))
                if row.get("collection_method") == "registry_official_product_link_v478":
                    self.assertTrue(row.get("release_date_evidence"))

    def test_review_queue_retains_sources_without_promotion(self):
        data = json.loads((ROOT / "releases.json").read_text(encoding="utf-8"))
        held = data.get("release_date_review_items", [])
        self.assertEqual(data.get("release_date_review_count", 0), len(held))
        published = data.get("items", []) + data.get("archive_items", [])
        for row in held:
            if row.get("collection_method") != "registry_official_product_link_v478":
                continue
            with self.subTest(name=row.get("name", "")):
                self.assertTrue(row.get("release_date_review_required"))
                self.assertTrue(row.get("source", "").startswith("https://"))
                self.assertFalse(update_releases.valid(row))
                self.assertNotIn(row, published)

    def test_registry_recheck_keeps_legacy_evidence(self):
        old = {
            "game": "Elestrals", "region": "US",
            "name": "Rules and Set FAQ - Snowshade Edition",
            "source": "https://www.elestrals.com/news/snowshade-set-faq",
            "collection_method": "registry_official_product_link_v478",
            "release_date": "2026-10-05",
        }
        accepted, held = update_releases.registry_date_review([old], [])
        self.assertEqual([], accepted)
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0]["release_date"], old["release_date"])
        self.assertEqual(held[0]["source"], old["source"])
        self.assertTrue(held[0]["release_date_review_required"])


if __name__ == "__main__":
    unittest.main()

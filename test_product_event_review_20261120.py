"""Review-only evidence for official product pages misclassified as card events."""
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
PRODUCT_URLS = {
    "https://world.digimoncard.com/products/deck/st-26/",
    "https://en.onepiece-cardgame.com/products/?subcategory=boosters",
}


class ProductEventReviewTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = json.loads((ROOT / "promo_events.json").read_text(encoding="utf-8"))

    def test_product_pages_not_exposed_as_events(self):
        reviewed = self.snapshot["product_release_review_queue"]
        self.assertTrue(PRODUCT_URLS.issubset({
            row.get("source") for row in reviewed
        }))
        self.assertEqual(len(reviewed), self.snapshot["product_release_review_count"])
        for lane in ("items", "archive_items"):
            self.assertFalse(any(
                row.get("source") in PRODUCT_URLS or
                (row.get("category") == "release" and
                 "/products/" in str(row.get("source", "")).lower())
                for row in self.snapshot[lane]
            ), lane)

    def test_original_review_evidence_and_old_collection_clock_are_preserved(self):
        self.assertIn("자동승격 금지", self.snapshot["product_release_review_policy"])
        latest = datetime.fromisoformat(self.snapshot["updated_at"].replace("Z", "+00:00"))
        self.assertIsNotNone(latest.utcoffset(), "Freshness evidence needs an aware timestamp")
        self.assertLessEqual(latest, datetime.now(timezone.utc) + timedelta(minutes=5))
        for row in self.snapshot["product_release_review_queue"]:
            self.assertEqual("release", row["category"])
            self.assertEqual("official", row["source_grade"])
            self.assertTrue(row["name_native"])
            self.assertTrue(row["discovered_at"])
            self.assertTrue(row["link_checked_at"])
            discovered = datetime.fromisoformat(row["discovered_at"].replace("Z", "+00:00"))
            self.assertIsNotNone(discovered.utcoffset())
            self.assertLessEqual(discovered, latest)
        self.assertGreaterEqual(len(self.snapshot["items"]), 20)
        self.assertGreaterEqual(len(self.snapshot["archive_items"]), 20)

    def test_historical_product_observation_does_not_claim_new_verification(self):
        for row in self.snapshot["product_release_review_queue"]:
            self.assertIn("discovered_at", row)
            self.assertIn("link_checked_at", row)
            self.assertNotIn("freshly_verified_at", row)
        self.assertFalse(any(
            str(row.get("source", "")).startswith("http://")
            for row in self.snapshot["product_release_review_queue"]
        ))


if __name__ == "__main__":
    unittest.main()

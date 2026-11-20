"""Review-only evidence for official product pages misclassified as card events."""
from __future__ import annotations
import json
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
        self.assertEqual(PRODUCT_URLS, {
            row.get("source") for row in self.snapshot["product_release_review_queue"]
        })
        self.assertEqual(2, self.snapshot["product_release_review_count"])
        for lane in ("items", "archive_items"):
            self.assertFalse(any(
                row.get("source") in PRODUCT_URLS for row in self.snapshot[lane]
            ), lane)

    def test_original_review_evidence_and_old_collection_clock_are_preserved(self):
        self.assertEqual("2026-10-08T23:35:21+00:00", self.snapshot["updated_at"])
        self.assertIn("자동승격 금지", self.snapshot["product_release_review_policy"])
        for row in self.snapshot["product_release_review_queue"]:
            self.assertEqual("release", row["category"])
            self.assertEqual("official", row["source_grade"])
            self.assertTrue(row["name_native"])
            self.assertTrue(row["discovered_at"])
            self.assertTrue(row["link_checked_at"])
        self.assertGreaterEqual(len(self.snapshot["items"]), 20)
        self.assertGreaterEqual(len(self.snapshot["archive_items"]), 20)

    def test_review_rows_are_not_treated_as_successful_fresh_collection(self):
        self.assertEqual(27, len(self.snapshot["items"]))
        self.assertEqual(63, len(self.snapshot["archive_items"]))
        self.assertTrue(self.snapshot["updated_at"].startswith("2026-10-08"))


if __name__ == "__main__":
    unittest.main()

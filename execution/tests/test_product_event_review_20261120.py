"""Offline regressions for product-event quarantine before successor integration."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from execution.product_event_quarantine import separate_product_release_candidates

ROOT = Path(__file__).resolve().parents[2]
PRODUCT_URLS = {
    "https://world.digimoncard.com/products/deck/st-26/",
    "https://en.onepiece-cardgame.com/products/?subcategory=boosters",
    "https://en.onepiece-cardgame.com/products/?subcategory=others",
}


class ProductEventReviewTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = json.loads(
            (ROOT / "promo_events.json").read_text(encoding="utf-8")
        )

    def test_both_real_product_pages_are_quarantined_not_published(self):
        original = deepcopy(self.snapshot)
        transformed = separate_product_release_candidates(self.snapshot)
        self.assertEqual(original, self.snapshot, "Caller snapshot must stay unchanged")
        reviewed = transformed["product_release_review_queue"]
        self.assertTrue(PRODUCT_URLS.issubset({row["source"] for row in reviewed}))
        for lane in ("items", "archive_items"):
            self.assertFalse(any(
                row.get("source") in PRODUCT_URLS for row in transformed[lane]
            ), lane)
        self.assertEqual(
            self.snapshot["updated_at"], transformed["updated_at"],
            "Classification is not a fresh collection",
        )
        self.assertEqual(transformed,
                         separate_product_release_candidates(transformed),
                         "Repeated classification cannot destroy or resurrect data")

    def test_invalid_official_looking_host_is_not_laundered(self):
        row = {
            "category": "release",
            "source": "https://unapproved.invalid/products/deck/st-26/",
        }
        value = {"items": [row], "archive_items": []}
        transformed = separate_product_release_candidates(value)
        self.assertEqual([row], transformed["items"])
        self.assertEqual([], transformed["product_release_review_queue"])

    def test_unrelated_valid_event_and_provenance_are_unchanged(self):
        original = deepcopy(self.snapshot)
        transformed = separate_product_release_candidates(self.snapshot)
        known = {row["source"] for row in transformed["product_release_review_queue"]}
        for lane in ("items", "archive_items"):
            expected = [row for row in original[lane] if row.get("source") not in known]
            self.assertEqual(expected, transformed[lane])
        self.assertEqual(original["social_topic_source_updated_at"],
                         transformed["social_topic_source_updated_at"])

    def test_invalid_shapes_fail_closed_without_mutation(self):
        for value in (None, {}, {"items": [], "archive_items": "bad"},
                      {"items": [42], "archive_items": []},
                      {"items": [], "archive_items": [],
                       "product_release_review_queue": "bad"}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                separate_product_release_candidates(value)

    def test_merchandise_product_page_is_review_only_without_event_promotion(self):
        original = deepcopy(self.snapshot)
        transformed = separate_product_release_candidates(self.snapshot)
        merch = "https://en.onepiece-cardgame.com/products/?subcategory=others"
        reviewed = [row for row in transformed["product_release_review_queue"]
                    if row.get("source") == merch]
        self.assertEqual(1, len(reviewed))
        self.assertEqual("merch", reviewed[0]["category"])
        for lane in ("items", "archive_items"):
            self.assertFalse(any(row.get("source") == merch
                                 for row in transformed[lane]))
        self.assertEqual(original, self.snapshot)
        self.assertEqual(original["updated_at"], transformed["updated_at"])

    def test_invalid_warning_ledger_without_product_is_rejected(self):
        # Even an empty event collection cannot launder a malformed ledger.
        bad = {"items": [], "archive_items": [],
               "collection_errors": {"error": "bad JSON shape"}}
        with self.assertRaisesRegex(ValueError, "INVALID_EVENT_COLLECTION_ERRORS"):
            separate_product_release_candidates(bad)

    def test_review_queue_overflow_is_rejected(self):
        row = next(r for r in self.snapshot["items"]
                   if r.get("source") in PRODUCT_URLS)
        sample = {"items": [{**row, "name_ko": str(i)} for i in range(65)],
                  "archive_items": []}
        before = deepcopy(sample)
        with self.assertRaisesRegex(ValueError, "PRODUCT_REVIEW_QUEUE_OVERFLOW"):
            separate_product_release_candidates(sample)
        self.assertEqual(before, sample)

    def test_existing_collection_error_history_is_not_deduplicated(self):
        row = next(r for r in self.snapshot["items"]
                   if r.get("source") in PRODUCT_URLS)
        warnings = ["previous 403", "previous 403", "previous timeout"]
        sample = {"items": [deepcopy(row)], "archive_items": [],
                  "collection_errors": warnings}
        original = deepcopy(sample)
        transformed = separate_product_release_candidates(sample)
        self.assertEqual(original, sample)
        self.assertEqual(warnings, transformed["collection_errors"][:len(warnings)])
        self.assertEqual(len(warnings) + 1, len(transformed["collection_errors"]))
        self.assertEqual(transformed, separate_product_release_candidates(transformed))

    def test_existing_notice_does_not_duplicate_original_warnings(self):
        row = next(r for r in self.snapshot["items"]
                   if r.get("source") in PRODUCT_URLS)
        from execution.product_event_quarantine import NOTICE
        warnings = ["previous 403", NOTICE, "previous 403"]
        sample = {"items": [deepcopy(row)], "archive_items": [],
                  "collection_errors": warnings}
        self.assertEqual(warnings,
                         separate_product_release_candidates(sample)["collection_errors"])


if __name__ == "__main__":
    unittest.main()

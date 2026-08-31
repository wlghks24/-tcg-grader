#!/usr/bin/env python3
from __future__ import annotations

import unittest

import graded_photo_manual_pair_queue as queue


class ManualPairQueueTests(unittest.TestCase):
    def test_identity_requires_supported_grader_and_certification(self):
        self.assertEqual(queue._identity({"company": "PSA", "certification_id": "12345678"}), ("PSA", "12345678"))
        self.assertEqual(queue._identity({"company": "PSA", "certification_id": ""}), ("", ""))
        self.assertEqual(queue._identity({"company": "OTHER", "certification_id": "12345678"}), ("", ""))

    def test_single_photo_is_rejected(self):
        row = {"game": "pokemon", "image_urls": ["https://example.com/a.jpg"]}
        self.assertIsNone(queue._pair_from_row(row))

    def test_two_unlabelled_photos_without_front_back_evidence_are_rejected(self):
        row = {"game": "pokemon", "title": "PSA 10 card", "image_urls": [
            "https://example.com/a.jpg", "https://example.com/b.jpg",
        ]}
        self.assertIsNone(queue._pair_from_row(row))

    def test_explicit_front_back_urls_are_accepted(self):
        row = {
            "game": "onepiece",
            "front_image_url": "https://example.com/front.jpg",
            "back_image_url": "https://example.com/back.jpg",
        }
        pair = queue._pair_from_row(row)
        self.assertIsNotNone(pair)
        self.assertEqual(pair[2], "explicit_fields")

    def test_listing_declaring_front_back_with_gallery_is_accepted(self):
        row = {
            "game": "naruto",
            "title": "BGS slab front and back photos",
            "image_urls": ["https://example.com/a.jpg", "https://example.com/b.jpg"],
        }
        pair = queue._pair_from_row(row)
        self.assertIsNotNone(pair)
        self.assertEqual(pair[2], "listing_declares_front_back")

    def test_pair_key_changes_with_certification(self):
        row = {"game": "pokemon", "url": "https://example.com/listing"}
        one = queue._pair_key(row, "https://example.com/front.jpg", "https://example.com/back.jpg", "PSA", "12345678")
        two = queue._pair_key(row, "https://example.com/front.jpg", "https://example.com/back.jpg", "PSA", "87654321")
        self.assertNotEqual(one, two)


if __name__ == "__main__":
    unittest.main()

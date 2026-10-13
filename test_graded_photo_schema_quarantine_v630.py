"""Regression for fail-closed graded-photo row quarantine (V630)."""
import copy
import unittest

from graded_photo_multi_source import _filter_invalid_photo_candidates


def _candidate(**overrides):
    row = {
        "source_id": "ebay_public",
        "company": "PSA",
        "game": "pokemon",
        "url": "https://www.ebay.com/itm/123456",
        "official_result": False,
        "image_url": "",
    }
    row.update(overrides)
    return row


class GradedPhotoSchemaQuarantineV630Tests(unittest.TestCase):
    def test_valid_candidate_survives_unchanged(self):
        row = _candidate()
        before = copy.deepcopy(row)
        kept, rejected = _filter_invalid_photo_candidates([row])
        self.assertEqual([before], kept)
        self.assertEqual([], rejected)
        self.assertEqual(before, row)

    def test_insecure_url_rejected_without_publishable_metadata(self):
        unsafe = _candidate(url="http://127.0.0.1/private", certification_id="SECRET123")
        kept, rejected = _filter_invalid_photo_candidates([unsafe])
        self.assertEqual([], kept)
        self.assertEqual(1, len(rejected))
        self.assertEqual("ebay_public", rejected[0]["source_id"])
        self.assertNotIn("private", repr(rejected))
        self.assertNotIn("SECRET123", repr(rejected))

    def test_unverified_claiming_official_grade_is_quarantined(self):
        unsafe = _candidate(official_result=True, certification_id="", official_grade=10)
        kept, rejected = _filter_invalid_photo_candidates([unsafe])
        self.assertEqual([], kept)
        self.assertEqual(1, len(rejected))

    def test_mixed_batch_keeps_valid_and_quarantines_only_invalid(self):
        valid = _candidate()
        unsafe = _candidate(company="FAKE")
        kept, rejected = _filter_invalid_photo_candidates([valid, unsafe])
        self.assertEqual([valid], kept)
        self.assertEqual([{"row_index": 1, "source_id": "ebay_public",
                           "action": "quarantine_invalid_security_schema"}], rejected)

    def test_empty_batch_preserves_empty_without_false_rejections(self):
        self.assertEqual(([], []), _filter_invalid_photo_candidates([]))


if __name__ == "__main__":
    unittest.main()

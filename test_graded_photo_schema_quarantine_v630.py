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

    def test_untrusted_source_id_is_not_exposed_in_rejection_audit(self):
        secret = 'PRIVATE_TOKEN_12345\\nhttps://private.example/unsafe'
        unsafe = _candidate(source_id=secret, url='http://127.0.0.1/')
        kept, rejected = _filter_invalid_photo_candidates([unsafe])
        self.assertEqual([], kept)
        self.assertEqual('unknown', rejected[0]['source_id'])
        self.assertNotIn('PRIVATE_TOKEN_12345', repr(rejected))
        self.assertNotIn('private.example', repr(rejected))

    def test_invalid_rows_are_rejected_before_feedback_and_legacy_audit(self):
        from pathlib import Path
        collector = (Path(__file__).resolve().parent / 'graded_photo_multi_source.py').read_text(encoding='utf-8')
        body = collector.split('def _collect_once()->dict:', 1)[1]
        gate = body.index('rows,schema_rejected=_filter_invalid_photo_candidates(rows)')
        self.assertLess(gate, body.index('learning_feedback=record_official_feedback(rows)'))
        self.assertLess(gate, body.index('rows,cleanup_stats,cleanup_audit=_review_and_prune_quarantine_v157(rows,previous_rows)'))

    def test_audit_source_allowlist_is_initialized_after_provider_registry(self):
        from pathlib import Path
        collector = (Path(__file__).resolve().parent / 'graded_photo_multi_source.py').read_text(encoding='utf-8')
        self.assertLess(collector.index('SOURCES=('), collector.index('REJECTION_AUDIT_SOURCE_IDS ='))

    def test_empty_batch_preserves_empty_without_false_rejections(self):
        self.assertEqual(([], []), _filter_invalid_photo_candidates([]))


if __name__ == "__main__":
    unittest.main()

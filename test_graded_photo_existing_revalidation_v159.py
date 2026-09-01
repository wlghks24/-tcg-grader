#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

import graded_photo_existing_revalidation_v159 as mod


class ExistingCandidateRevalidationV159Tests(unittest.TestCase):
    def _common_patches(self, payload, *, verify=None, reference_count=1):
        written = {}

        def fake_write(path, data, **kwargs):
            written['payload'] = data

        def fake_verify(rows, registry, max_live=0):
            out = [dict(row) for row in rows]
            if verify:
                out = verify(out)
            return out, {'live_attempts': 0, 'live_verified': 0}

        patches = [
            patch.object(mod.gp, '_load', return_value=payload),
            patch.object(mod.gp, 'atomic_write_json', side_effect=fake_write),
            patch.object(mod.gp, 'enrich_rows', side_effect=lambda rows, limit, workers: ([dict(r) for r in rows], {'attempted': len(rows), 'validated': 0, 'ocr_readable': 0, 'certs_extracted': 0})),
            patch.object(mod.gp, '_registry', return_value={}),
            patch.object(mod.gp, '_official_verify_rows', side_effect=fake_verify),
            patch.object(mod.gp, '_resolve_cert_conflicts', side_effect=lambda rows: rows),
            patch.object(mod.gp, '_resolve_image_conflicts', side_effect=lambda rows: (rows, {})),
            patch.object(mod.gp, '_apply_measurement_photo_quality', side_effect=lambda rows: rows),
            patch.object(mod.gp, '_save_reference_learning', return_value={'summary': {'reference_learning_count': reference_count}}),
            patch.object(mod.gp, '_aggregate_dimension_stats', return_value=({}, {})),
            patch.object(mod.gp, 'record_official_feedback', return_value={}),
        ]
        return patches, written

    def test_confirmed_unusable_pruned_but_transient_http_failure_kept(self):
        payload = {
            'summary': {'reference_learning_count': 1},
            'records': [
                {
                    'url': 'https://example.com/verified', 'image_url': 'https://example.com/v.jpg',
                    'company': 'PSA', 'certification_id': '12345678', 'grade': 10,
                    'official_result': True, 'status': 'verified_reference', 'image_validated': True,
                },
                {
                    'url': 'https://example.com/no-image', 'image_url': '',
                    'company': 'BGS', 'grade': 9, 'official_result': False,
                    'quarantine_review_count': 1,
                },
                {
                    'url': 'https://example.com/retry', 'image_url': 'https://example.com/retry.jpg',
                    'company': 'CGC', 'certification_id': '87654321', 'grade': 9,
                    'official_result': False, 'image_probe_status': 'failed',
                    'image_probe_error': 'HTTPError', 'quarantine_review_count': 1,
                },
            ],
        }
        patches, written = self._common_patches(payload)
        for item in patches:
            item.start()
        try:
            result = mod.revalidate_existing_candidates()
        finally:
            for item in reversed(patches):
                item.stop()

        self.assertTrue(result['ok'])
        self.assertEqual(result['summary']['existing_candidates_reviewed'], 3)
        self.assertEqual(result['summary']['quarantine_pruned'], 1)
        rows = written['payload']['records']
        self.assertEqual(len(rows), 2)
        self.assertTrue(any(row.get('official_result') is True for row in rows))
        retry = next(row for row in rows if row.get('url', '').endswith('/retry'))
        self.assertEqual(retry.get('image_probe_status'), 'retryable_failed')
        self.assertTrue(retry.get('image_revalidation_retryable'))
        self.assertTrue(written['payload']['policy']['temporary_network_and_rate_limit_failures_preserved'])

    def test_fresh_official_match_is_promoted_to_reference_learning(self):
        payload = {
            'summary': {'reference_learning_count': 0},
            'records': [
                {
                    'url': 'https://example.com/card', 'image_url': 'https://example.com/card.jpg',
                    'company': 'PSA', 'certification_id': '160600294', 'grade': 10,
                    'official_result': False, 'image_validated': True, 'ocr_label_text': 'PSA 10 160600294',
                }
            ],
        }

        def verify(rows):
            rows[0]['official_result'] = True
            rows[0]['official_grade'] = 10
            return rows

        patches, written = self._common_patches(payload, verify=verify, reference_count=1)
        for item in patches:
            item.start()
        try:
            result = mod.revalidate_existing_candidates()
        finally:
            for item in reversed(patches):
                item.stop()

        self.assertEqual(result['summary']['promoted_verified'], 1)
        self.assertEqual(result['summary']['promoted_learning'], 1)
        self.assertEqual(result['summary']['verified_references'], 1)
        self.assertEqual(written['payload']['records'][0]['status'], 'verified_reference')
        self.assertEqual(written['payload']['records'][0]['learning_eligibility'], 'reference_learning_only')


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import tempfile
import unittest
from pathlib import Path

import verified_grade_learning_v135 as learning


class VerifiedGradeLearningV135Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.originals = {
            'ROOT': learning.ROOT,
            'LEARNING_STORE': learning.LEARNING_STORE,
            'VERIFIED_CERTS': learning.VERIFIED_CERTS,
            'VISION_CALIBRATION': learning.VISION_CALIBRATION,
        }
        learning.ROOT = root
        learning.LEARNING_STORE = root / 'learning_store.json'
        learning.VERIFIED_CERTS = root / 'verified_certifications.json'
        learning.VISION_CALIBRATION = root / 'vision_calibration.json'

    def tearDown(self):
        for key, value in self.originals.items():
            setattr(learning, key, value)
        self.temp.cleanup()

    def _registry(self, rows):
        learning.VERIFIED_CERTS.write_text(
            json.dumps({'version': 1, 'certifications': rows}), encoding='utf-8'
        )

    def _store(self, rows):
        learning.LEARNING_STORE.write_text(
            json.dumps({'version': 3, 'v99_validation': rows, 'v30_validation': [], 'v11_validation': []}),
            encoding='utf-8',
        )

    @staticmethod
    def _verified(company='PSA', cert='10000001', grade=9):
        return {'company': company, 'certification_id': cert, 'grade': grade, 'verified': True}

    @staticmethod
    def _row(company='PSA', cert='10000001', actual=9, raw=10, **extra):
        return {
            'company': company,
            'actual': actual,
            'pred': raw,
            'raw_pred': raw,
            'official_result': True,
            'certification_id': cert,
            'mode': 'raw',
            'game': 'pokemon',
            'card_id': f'card-{cert}',
            **extra,
        }

    def test_client_official_flag_without_registry_is_excluded(self):
        self._registry([])
        self._store([self._row()])
        rows, audit = learning.eligible_training_rows()
        self.assertEqual(rows, [])
        self.assertEqual(audit['not_in_verified_registry'], 1)

    def test_exact_registry_match_is_eligible(self):
        self._registry([self._verified()])
        self._store([self._row()])
        rows, audit = learning.eligible_training_rows()
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]['server_verified'])
        self.assertEqual(audit['eligible'], 1)

    def test_registry_grade_conflict_is_excluded(self):
        self._registry([self._verified(grade=8)])
        self._store([self._row(actual=9)])
        rows, audit = learning.eligible_training_rows()
        self.assertEqual(rows, [])
        self.assertEqual(audit['registry_grade_conflict'], 1)

    def test_raw_prediction_is_mandatory(self):
        self._registry([self._verified()])
        row = self._row()
        row.pop('raw_pred')
        self._store([row])
        rows, audit = learning.eligible_training_rows()
        self.assertEqual(rows, [])
        self.assertEqual(audit['missing_independent_raw_prediction'], 1)

    def test_slab_reference_never_trains_raw_calibration(self):
        self._registry([self._verified()])
        self._store([self._row(mode='slab')])
        rows, audit = learning.eligible_training_rows()
        self.assertEqual(rows, [])
        self.assertEqual(audit['slab_reference_not_raw_calibration'], 1)

    def test_submit_requires_successful_official_lookup(self):
        self._registry([])
        result = learning.submit_verified_sample(
            {'company': 'PSA', 'certification_id': '10000001', 'actual_grade': 9, 'raw_pred': 10, 'mode': 'raw'},
            verifier=lambda c, n, g: {'ok': True, 'verified': False, 'grade': None},
        )
        self.assertFalse(result['accepted'])
        self.assertFalse(learning.LEARNING_STORE.exists())
        self.assertEqual(learning.registry_index(), {})

    def test_successful_submit_persists_verified_anchor_and_training_row(self):
        self._registry([])
        result = learning.submit_verified_sample(
            {
                'company': 'PSA', 'certification_id': '10000001', 'actual_grade': 9,
                'raw_pred': 10, 'pred': 10, 'mode': 'raw', 'game': 'pokemon', 'card_key': 'p|set|card|1',
            },
            verifier=lambda c, n, g: {
                'ok': True, 'verified': True, 'grade': 9,
                'official_url': 'https://www.psacard.com/cert/10000001/psa',
            },
        )
        self.assertTrue(result['accepted'])
        self.assertIn('PSA|10000001', learning.registry_index())
        rows, audit = learning.eligible_training_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(audit['eligible'], 1)

    def test_cross_validated_model_is_downward_only(self):
        certs = []
        rows = []
        for i in range(10):
            cert = f'900000{i:02d}'
            certs.append(self._verified(cert=cert, grade=9))
            rows.append(self._row(cert=cert, actual=9, raw=10, card_id=f'independent-{i}'))
        self._registry(certs)
        self._store(rows)
        status = learning.model_status()
        psa = status['companies']['PSA']
        self.assertEqual(status['verified_training_rows'], 10)
        self.assertTrue(psa['enabled'])
        self.assertLess(psa['correction'], 0)
        self.assertGreaterEqual(psa['correction'], -0.75)
        self.assertFalse(status['policy']['upward_correction_allowed'])

    def test_duplicate_certification_is_deduplicated(self):
        self._registry([self._verified()])
        self._store([self._row(card_id='a'), self._row(card_id='b')])
        rows, _ = learning.eligible_training_rows()
        self.assertEqual(len(rows), 1)


if __name__ == '__main__':
    unittest.main()

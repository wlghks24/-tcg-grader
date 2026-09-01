#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import base64
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pending_official_candidate_v161 as mod


class PendingOfficialCandidateV161Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.out = self.root / 'graded_photo_candidates.json'
        self.proof = self.root / 'proof'
        self.row = {
            'company': 'BGS', 'game': 'onepiece', 'grade': 10.0,
            'certification_id': '100017423404', 'source': 'eBay 공개검색',
            'title': 'BGS 10 One Piece', 'image_url': 'https://example.com/card.jpg',
            'official_result': False, 'status': 'quarantine_candidate',
            'quarantine_reasons': ['official_verification_missing'],
        }
        mod.gp.atomic_write_json(self.out, {'records': [self.row], 'summary': {'total_candidates': 1}}, suffix='.tmp')
        self.patches = [
            mock.patch.object(mod.gp, 'OUT', self.out),
            mock.patch.object(mod, 'PROOF_ROOT', self.proof),
            mock.patch.object(mod, 'ROOT', self.root),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        self.tmp.cleanup()

    def test_public_status_lists_only_pending_resolved_candidate(self):
        status = mod.public_status()
        self.assertTrue(status['ok'])
        self.assertEqual(status['pending_count'], 1)
        row = status['candidates'][0]
        self.assertEqual(row['company'], 'BGS')
        self.assertEqual(row['certification_id'], '100017423404')
        self.assertEqual(row['grade'], 10.0)

    def test_exact_manual_proof_promotes_reference(self):
        candidate_id = mod.public_status()['candidates'][0]['candidate_id']
        jpeg = b'\xff\xd8\xff' + b'x' * 100
        data_url = 'data:image/jpeg;base64,' + base64.b64encode(jpeg).decode('ascii')
        evidence = {'company': 'BGS', 'certification_id': '100017423404', 'grade': 10.0}
        exact = {
            'matched': True, 'company_match': True, 'cert_match': True,
            'grade_match': True, 'explicit_conflicts': [],
            'match_mode': 'official_page_company_cert_grade_ocr',
        }
        with mock.patch.object(mod.manual_photo, '_ocr_image', return_value=('BGS 100017423404 GRADE 10', None, {}, evidence)), \
             mock.patch.object(mod.manual_proof, '_match_proof', return_value=exact), \
             mock.patch.object(mod.gp, '_save_reference_learning', return_value={'summary': {'reference_learning_count': 1}}), \
             mock.patch.object(mod.gp, 'record_official_feedback', return_value=None):
            result = mod.submit({'candidate_id': candidate_id, 'proof_image': data_url})
        self.assertTrue(result['accepted'])
        payload = mod.gp._load(self.out, {})
        row = payload['records'][0]
        self.assertTrue(row['official_result'])
        self.assertTrue(row['manual_official_candidate_verified'])
        self.assertEqual(row['verification_state'], 'manual_official_verified')
        self.assertFalse(row['raw_grade_calibration_eligible'])

    def test_mismatch_does_not_promote(self):
        candidate_id = mod.public_status()['candidates'][0]['candidate_id']
        jpeg = b'\xff\xd8\xff' + b'x' * 100
        data_url = 'data:image/jpeg;base64,' + base64.b64encode(jpeg).decode('ascii')
        mismatch = {
            'matched': False, 'company_match': True, 'cert_match': True,
            'grade_match': False, 'explicit_conflicts': ['official_proof_grade_mismatch'],
            'match_mode': None,
        }
        with mock.patch.object(mod.manual_photo, '_ocr_image', return_value=('BGS 100017423404 GRADE 9', None, {}, {'company': 'BGS', 'certification_id': '100017423404', 'grade': 9.0})), \
             mock.patch.object(mod.manual_proof, '_match_proof', return_value=mismatch):
            result = mod.submit({'candidate_id': candidate_id, 'proof_image': data_url})
        self.assertFalse(result['accepted'])
        payload = mod.gp._load(self.out, {})
        self.assertFalse(payload['records'][0]['official_result'])


if __name__ == '__main__':
    unittest.main()

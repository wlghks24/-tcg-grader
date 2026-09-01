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
        self.negative = self.root / 'negative-proof'
        self.rejections = self.root / 'rejections.json'
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
            mock.patch.object(mod, 'NEGATIVE_PROOF_ROOT', self.negative),
            mock.patch.object(mod, 'REJECTION_LOG', self.rejections),
            mock.patch.object(mod, 'ROOT', self.root),
        ]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in reversed(self.patches):
            patch.stop()
        self.tmp.cleanup()

    @staticmethod
    def _jpeg_url():
        jpeg = b'\xff\xd8\xff' + b'x' * 100
        return 'data:image/jpeg;base64,' + base64.b64encode(jpeg).decode('ascii')

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
            result = mod.submit({'candidate_id': candidate_id, 'proof_image': self._jpeg_url()})
        self.assertTrue(result['accepted'])
        payload = mod.gp._load(self.out, {})
        row = payload['records'][0]
        self.assertTrue(row['official_result'])
        self.assertTrue(row['manual_official_candidate_verified'])
        self.assertEqual(row['verification_state'], 'manual_official_verified')
        self.assertFalse(row['raw_grade_calibration_eligible'])

    def test_mismatch_does_not_promote(self):
        candidate_id = mod.public_status()['candidates'][0]['candidate_id']
        mismatch = {
            'matched': False, 'company_match': True, 'cert_match': True,
            'grade_match': False, 'explicit_conflicts': ['official_proof_grade_mismatch'],
            'match_mode': None,
        }
        with mock.patch.object(mod.manual_photo, '_ocr_image', return_value=('BGS 100017423404 GRADE 9', None, {}, {'company': 'BGS', 'certification_id': '100017423404', 'grade': 9.0})), \
             mock.patch.object(mod.manual_proof, '_match_proof', return_value=mismatch):
            result = mod.submit({'candidate_id': candidate_id, 'proof_image': self._jpeg_url()})
        self.assertFalse(result['accepted'])
        payload = mod.gp._load(self.out, {})
        self.assertFalse(payload['records'][0]['official_result'])

    def test_no_record_proof_archives_and_deletes_only_unverified_candidate(self):
        candidate_id = mod.public_status()['candidates'][0]['candidate_id']
        with mock.patch.object(mod.manual_photo, '_ocr_image', return_value=('BECKETT 검색된 기록이 없습니다.', None, {}, {'company': 'BGS'})), \
             mock.patch.object(mod.gp, '_save_reference_learning', return_value={'summary': {'reference_learning_count': 0}}), \
             mock.patch.object(mod.gp, 'record_official_feedback', return_value=None):
            result = mod.submit({
                'action': 'official_not_found',
                'candidate_id': candidate_id,
                'proof_image': self._jpeg_url(),
                'certification_id_confirmation': '100017423404',
                'confirm_no_record': True,
            })
        self.assertTrue(result['accepted'])
        self.assertTrue(result['deleted'])
        self.assertEqual(result['deleted_rows'], 1)
        self.assertTrue(result['negative_proof_archived'])
        self.assertTrue(result['ocr_negative_text_detected'])
        payload = mod.gp._load(self.out, {})
        self.assertEqual(payload['records'], [])
        rejection = mod.gp._load(self.rejections, {})['rejections'][0]
        self.assertEqual(rejection['reason'], 'official_record_not_found_user_confirmed')
        self.assertFalse(rejection['learning_eligible'])
        self.assertFalse(rejection['raw_grade_calibration_eligible'])

    def test_no_record_delete_requires_exact_certificate_confirmation(self):
        candidate_id = mod.public_status()['candidates'][0]['candidate_id']
        with self.assertRaises(ValueError):
            mod.submit({
                'action': 'official_not_found',
                'candidate_id': candidate_id,
                'proof_image': self._jpeg_url(),
                'certification_id_confirmation': 'WRONG123',
                'confirm_no_record': True,
            })
        payload = mod.gp._load(self.out, {})
        self.assertEqual(len(payload['records']), 1)

    def test_rejection_registry_hides_recollected_same_cert_from_pending_manual_list(self):
        mod.gp.atomic_write_json(self.rejections, {
            'schema_version': 1,
            'rejections': [{
                'company': 'BGS', 'certification_id': '100017423404',
                'reason': 'official_record_not_found_user_confirmed',
            }],
        }, suffix='.tmp')
        status = mod.public_status()
        self.assertEqual(status['pending_count'], 0)


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
import inspect
import unittest
from unittest import mock

import grading_cert_verifier as verifier
import graded_photo_multi_source as gp
import manual_official_proof as proof


class ManualOnlyOfficialVerificationV192Tests(unittest.TestCase):
    def test_global_verifier_is_hard_disabled(self):
        self.assertTrue(verifier.automatic_lookup_disabled())
        with mock.patch.object(verifier, '_fetch') as fetch:
            result=verifier.verify_cert('BRG','0346643',expected_grade=10)
        fetch.assert_not_called()
        self.assertTrue(result.get('manual_verification_required'))
        self.assertFalse(result.get('verified'))
        self.assertEqual(result.get('official_url'),'https://break.co.kr/certification/0346643')

    def test_candidate_collection_makes_zero_live_cert_requests(self):
        rows=[{'company':'BRG','game':'pokemon','grade':10.0,'certification_id':'0346643'}]
        with mock.patch.object(gp,'verify_cert') as live, \
             mock.patch.object(gp,'_load',return_value={}), \
             mock.patch.object(gp,'atomic_write_json'):
            _rows,stats=gp._official_verify_rows(rows,{},max_live=10)
        live.assert_not_called()
        self.assertEqual(int(stats.get('live_attempts') or 0),0)

    def test_manual_proof_is_final_official_reference_but_not_raw(self):
        source=inspect.getsource(proof)
        self.assertIn('"manual_screenshot_sets_official_result": True',source)
        self.assertIn('"official_result": bool(matched)',source)
        self.assertIn('"verification_state": "manual_official_verified"',source)
        self.assertIn('"raw_grade_calibration_eligible": False',source)
        self.assertIn('"automatic_live_lookup_used": False',source)

    def test_ui_requires_explicit_third_step(self):
        bridge=open('manual_official_verify_bridge.js',encoding='utf-8').read()
        pending=open('pending_official_candidate_bridge_v161.js',encoding='utf-8').read()
        self.assertIn('③ 검증완료 등록',bridge)
        self.assertIn('proofDrafts',bridge)
        self.assertIn('③ 검증완료 등록',pending)
        self.assertNotIn('brgcard.com/certification',pending)
        self.assertIn('break.co.kr/certification/{cert}',open('grading_cert_verifier.py',encoding='utf-8').read())


if __name__=='__main__':
    unittest.main()

#!/usr/bin/env python3
import inspect
import unittest
from pathlib import Path
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

    def test_candidate_collection_has_no_live_cert_path_and_scrubs_stale_trust(self):
        rows=[{'company':'BRG','game':'pokemon','grade':10.0,'certification_id':'0346643',
               'official_result':True,'verification_method':'live_official_lookup','official_grade':10.0}]
        with mock.patch.object(gp,'atomic_write_json'):
            out,stats=gp._official_verify_rows(rows,{},max_live=10)
        source=inspect.getsource(gp._official_verify_rows)
        self.assertNotIn('verify_cert(',source)
        self.assertFalse(out[0].get('official_result'),out[0])
        self.assertTrue(out[0].get('manual_official_verification_required'),out[0])
        self.assertEqual(out[0].get('official_verification'),'manual_verification_required')
        self.assertEqual(int(stats.get('live_attempts') or 0),0)

    def test_manual_verified_registry_is_the_only_collector_promotion(self):
        rows=[{'company':'BRG','game':'pokemon','grade':10.0,'certification_id':'0346643'}]
        with mock.patch.object(gp,'atomic_write_json'):
            out,stats=gp._official_verify_rows(rows,{('BRG','0346643'):10.0},max_live=99)
        self.assertTrue(out[0].get('official_result'),out[0])
        self.assertEqual(out[0].get('verification_method'),'persisted_manual_verified_registry')
        self.assertFalse(out[0].get('manual_official_verification_required'),out[0])
        self.assertEqual(int(stats.get('registry_matches') or 0),1)

    def test_manual_proof_is_final_official_reference_but_not_raw(self):
        source=inspect.getsource(proof)
        self.assertIn('"manual_screenshot_sets_official_result": True',source)
        self.assertIn('"official_result": bool(matched)',source)
        self.assertIn('"verification_state": "manual_official_verified"',source)
        self.assertIn('"raw_grade_calibration_eligible": False',source)
        self.assertIn('"automatic_live_lookup_used": False',source)
        self.assertIn('"manual_screenshot_grade_may_use_exact_slab_ocr_fallback": False',source)
        self.assertNotIn('def _slab_identity_exact(',source)

    def test_ui_requires_explicit_third_step(self):
        bridge=Path('manual_official_verify_bridge.js').read_text(encoding='utf-8')
        pending=Path('pending_official_candidate_bridge_v161.js').read_text(encoding='utf-8')
        self.assertIn('③ 검증완료 등록',bridge)
        self.assertIn('proofDrafts',bridge)
        self.assertIn('③ 검증완료 등록',pending)
        self.assertNotIn('brgcard.com/certification',pending)
        self.assertIn('break.co.kr/certification/{cert}',Path('grading_cert_verifier.py').read_text(encoding='utf-8'))


if __name__=='__main__':
    unittest.main()

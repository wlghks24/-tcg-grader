import unittest
from execution.tablet_vision_readiness import assess

class VisionReadinessTests(unittest.TestCase):
    def test_missing_data_reports_both_blockers(self):
        result=assess([],{'seen':0})
        self.assertEqual(0,result['verified_calibration_rows'])
        self.assertTrue(all(not m['ready'] for m in result['models'].values()))
        self.assertFalse(result['production_model_changed'])

    def test_calibration_volume_cannot_fabricate_image_readiness(self):
        rows=[{'company':'PSA','game':'pokemon','card_id':str(i)} for i in range(2000)]
        result=assess(rows,{'not_in_verified_registry':12})
        self.assertEqual(2000,result['verified_calibration_rows'])
        self.assertEqual(2000,result['unique_calibration_cards'])
        self.assertEqual(12,result['rejected_row_reasons']['not_in_verified_registry'])
        self.assertFalse(result['raw_image_model_retrained'])
        self.assertTrue(all(not m['ready'] for m in result['models'].values()))

    def test_grader_game_identity_remain_separate(self):
        result=assess([{'company':c,'game':g,'card_id':'1'} for c,g in [('PSA','pokemon'),('BGS','pokemon'),('PSA','onepiece')]],{})
        self.assertEqual(3,result['unique_calibration_cards'])
        self.assertEqual({'BGS':1,'PSA':2},result['company_rows'])

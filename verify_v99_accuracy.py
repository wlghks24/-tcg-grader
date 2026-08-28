#!/usr/bin/env python3
import json, unittest
import grading_accuracy_v99 as v

def row(i,company='PSA',actual=9,raw=10,official=True,cert=None,confidence=90):
 return {'company':company,'actual':actual,'pred':raw,'raw_pred':raw,'official_result':official,
         'certification_id':cert or f'CERT-{company}-{i:04d}','card_id':f'CARD-{company}-{i:04d}',
         'vision':{'analysisConfidence':confidence,'surfaceConfidence':88}}

class V99AccuracyTests(unittest.TestCase):
 def test_psa_has_no_half_grade(self):self.assertEqual(v.quantize_down('PSA',9.9),9)
 def test_tag_has_no_9_5(self):self.assertEqual(v.quantize_down('TAG',9.9),9)
 def test_bgs_keeps_half_grade(self):self.assertEqual(v.quantize_down('BGS',9.7),9.5)
 def test_defect_monotonic(self):
  grades=[v.estimate_raw_grade(50,50,r,r,r,'BGS') for r in range(0,101,5)]
  self.assertTrue(all(a>=b for a,b in zip(grades,grades[1:])))
 def test_centering_monotonic(self):
  grades=[v.estimate_raw_grade(x,x,0,0,0,'PSA') for x in range(50,4,-5)]
  self.assertTrue(all(a>=b for a,b in zip(grades,grades[1:])))
 def test_edge_and_corner_can_limit_grade(self):
  clean=v.estimate_raw_grade(50,50,2,2,2,'BGS');edge=v.estimate_raw_grade(50,50,2,70,2,'BGS');corner=v.estimate_raw_grade(50,50,2,2,70,'BGS')
  self.assertGreater(clean,edge);self.assertGreater(clean,corner)
 def test_unverified_rejected(self):self.assertEqual(v.sanitize_rows({'v99_validation':[row(1,official=False)]}),[])
 def test_low_confidence_rejected(self):self.assertEqual(v.sanitize_rows({'v99_validation':[row(1,confidence=40)]}),[])
 def test_duplicate_cert_deduplicates(self):
  rows=v.sanitize_rows({'v99_validation':[row(1,cert='SAME1'),row(2,cert='SAME1')]});self.assertEqual(len(rows),1)
 def test_invalid_psa_half_actual_rejected(self):self.assertEqual(v.sanitize_rows({'v99_validation':[row(1,actual=9.5)]}),[])
 def test_raw_pred_prevents_feedback_loop(self):
  x=row(1);x['pred']=9;x['raw_pred']=10;clean=v.sanitize_rows({'v99_validation':[x]});self.assertEqual(clean[0]['raw_pred'],10)
 def test_consistent_overgrade_cv_enables_downward(self):
  clean=v.sanitize_rows({'v99_validation':[row(i) for i in range(30)]});m=v.train_company_calibration(clean)['PSA'];self.assertTrue(m['enabled']);self.assertLess(m['correction'],0);self.assertLess(m['cv_mae_after'],m['cv_mae_before'])
 def test_small_calibration_does_not_drop_whole_psa_grade(self):
  models={'PSA':{'enabled':True,'correction':-.25}}
  self.assertEqual(v.apply_calibration('PSA',10,models),10)
 def test_bgs_low_centering_public_gates(self):
  self.assertEqual(v.grade_by_center(35,15,'BGS'),7)
  self.assertEqual(v.grade_by_center(30,10,'BGS'),6)
 def test_cgc_nine_reachable(self):
  self.assertEqual(v.grade_by_center(40,40,'CGC'),9)
 def test_undergrade_never_enables_upward(self):
  clean=v.sanitize_rows({'v99_validation':[row(i,company='BGS',actual=10,raw=9) for i in range(30)]});m=v.train_company_calibration(clean)['BGS'];self.assertFalse(m['enabled']);self.assertEqual(m['correction'],0)
 def test_company_isolation(self):
  clean=v.sanitize_rows({'v99_validation':[row(i,company='TAG',actual=8,raw=9) for i in range(30)]});m=v.train_company_calibration(clean);self.assertTrue(m['TAG']['enabled']);self.assertEqual(m['PSA']['correction'],0)

 def test_tag_gem_mint_ten_centering_gate(self):
  self.assertEqual(v.grade_by_center(45,35,'TAG'),10)
  self.assertEqual(v.grade_by_center(40,25,'TAG'),9)
  self.assertEqual(v.grade_by_center(37.5,15,'TAG'),8.5)

 def test_tag_pristine_and_gem_mint_share_numeric_ten(self):
  self.assertEqual(v.grade_by_center(49,48,'TAG'),10)
  self.assertEqual(v.grade_by_center(45,35,'TAG'),10)

 def test_invalid_half_step_actual_rejected_for_bgs(self):
  self.assertEqual(v.sanitize_rows({'v99_validation':[row(1,company='BGS',actual=9.3)]}),[])

 def test_conflicting_same_cert_is_quarantined(self):
  a=row(1,cert='CONFLICT-1',actual=9);b=row(2,cert='CONFLICT-1',actual=8)
  self.assertEqual(v.sanitize_rows({'v99_validation':[a,b]}),[])

 def test_v99_rows_take_precedence_over_legacy_v30(self):
  modern=row(1,cert='MODERN-1',actual=9,raw=10);legacy=row(2,cert='MODERN-1',actual=7,raw=10)
  clean=v.sanitize_rows({'v99_validation':[modern],'v30_validation':[legacy]})
  self.assertEqual(len(clean),1);self.assertEqual(clean[0]['actual'],9)

 def test_card_key_groups_same_design(self):
  rows=[]
  for i in range(12):
   x=row(i,company='BRG',actual=9,raw=10);x['card_key']='same-design';x.pop('card_id',None);rows.append(x)
  clean=v.sanitize_rows({'v99_validation':rows});m=v.train_company_calibration(clean)['BRG']
  self.assertEqual(m['unique_cards'],1);self.assertFalse(m['enabled'])

 def test_invalid_company_safe(self):
  self.assertEqual(v.quantize_down('INVALID',9.9),1)
  self.assertEqual(v.apply_downward_correction('INVALID',10,-1),1)
  self.assertEqual(v.apply_calibration('INVALID',10,{}),1)

 def test_half_grade_evidence_threshold_is_consistent(self):
  self.assertEqual(v.apply_downward_correction('PSA',10,-.25),10)
  self.assertEqual(v.apply_downward_correction('PSA',10,-.5),9)

 def test_bgs_one_point_five_centering_reachable(self):
  self.assertEqual(v.quantize_down('BGS',v.grade_by_center(9,50,'BGS')),1.5)
 def test_single_outlier_does_not_flip_direction(self):
  rows=[row(i) for i in range(29)]+[row(99,actual=10,raw=1)];clean=v.sanitize_rows({'v99_validation':rows});m=v.train_company_calibration(clean)['PSA'];self.assertLessEqual(m['correction'],0)

if __name__=='__main__':
 suite=unittest.defaultTestLoader.loadTestsFromTestCase(V99AccuracyTests);res=unittest.TextTestRunner(verbosity=2).run(suite)
 print(json.dumps({'ok':res.wasSuccessful(),'tests':res.testsRun,'failures':len(res.failures),'errors':len(res.errors)}))
 raise SystemExit(0 if res.wasSuccessful() else 1)

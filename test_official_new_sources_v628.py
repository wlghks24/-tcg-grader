#!/usr/bin/env python3
"""V628: free official sealed product evidence and honest date coverage."""
import unittest, json, copy
from pathlib import Path
from datetime import date
from execution.official_box_coverage_audit_v623 import audit, CoverageError
from official_product_evidence_audit_v627 import build_report
R=Path(__file__).resolve().parent
class SourceV628(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.reg=json.loads((R/'tcg_game_registry.json').read_text(encoding='utf8'))
  cls.cat=json.loads((R/'tcg_official_product_catalog_v599.json').read_text(encoding='utf8'))
  cls.by_id={x['id']:x for x in cls.cat['products']}
 def test_product_coverage_not_market_completion(self):
  d=audit(self.reg,self.cat,as_of=date(2026,10,12))
  self.assertEqual((30,58,55,15,40),(d['registry_games'],d['reviewed_official_product_records'],d['declared_game_country_pairs'],d['pairs_with_any_official_product'],d['game_country_product_coverage_gaps']))
  rows={(x['game_id'],x['country']):x for x in d['cells']}
  self.assertEqual(1,rows[('naruto','US')]['official_box_count'])
  self.assertEqual(1,rows[('unionarena','US')]['official_box_count'])
  self.assertEqual(1,rows[('weiss-schwarz','US')]['official_booster_pack_count'])
 def test_product_specs_and_uncertain_date(self):
  a=self.by_id['naruto-mythos-US-konoha-2e-display']
  self.assertEqual((24,'10','',True),(a['packs_per_box'],a['cards_per_pack'],a['release_date'],a['release_date_unverified']))
  self.assertEqual(('NARUTO Mythos TCG','2nd'),(a['product_line'],a['edition']))
  self.assertEqual((16,'12'),(self.by_id['ua-US-UE16BT-box']['packs_per_box'],self.by_id['ua-US-UE16BT-box']['cards_per_pack']))
  self.assertEqual(4.99,self.by_id['ua-US-UE16BT-pack']['msrp']['amount'])
  self.assertNotIn('msrp',self.by_id['ua-US-UE16BT-box'])
  self.assertEqual((12,'8'),(self.by_id['ws-US-MKI-box']['packs_per_box'],self.by_id['ws-US-MKI-box']['cards_per_pack']))
 def test_missing_date_requires_flag_never_guesses_prerelease(self):
  bad=copy.deepcopy(self.cat);a=next(x for x in bad['products'] if x['id']=='naruto-mythos-US-konoha-2e-display')
  a.pop('release_date_unverified')
  with self.assertRaisesRegex(CoverageError,'MISSING_PRODUCT_RELEASE_DATE'):audit(self.reg,bad)
  a['release_date_unverified']=True;a['release_date']='2026-08-29'
  with self.assertRaisesRegex(CoverageError,'UNVERIFIED_RELEASE_DATE_CONFLICT'):audit(self.reg,bad)
 def test_official_hostname_spoofing_fails_closed(self):
  for id in ('naruto-mythos-US-konoha-2e-display','ua-US-UE16BT-pack','ws-US-MKI-box'):
   bad=copy.deepcopy(self.cat);a=next(x for x in bad['products'] if x['id']==id)
   a['source']=a['source'].replace(a['source'].split('/')[2],a['source'].split('/')[2]+'.evil.example')
   with self.subTest(id=id),self.assertRaisesRegex(CoverageError,'UNTRUSTED_OR_UNMATCHED_OFFICIAL_SOURCE'):audit(self.reg,bad)
 def test_evidence_unchanged_limitations(self):
  report=build_report(self.reg,self.cat,as_of=date(2026,10,12))
  self.assertEqual(58,report['product_sample_count'])
  self.assertEqual(47,report['missing_evidence_counts']['SOURCE_RECHECK_TIMESTAMP_NOT_RECORDED'])
  self.assertTrue(report['no_verified_completed_market_sales'])
  self.assertTrue(report['no_verified_hit_pull_rate'])
if __name__=='__main__':unittest.main(verbosity=2)

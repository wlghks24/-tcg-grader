#!/usr/bin/env python3
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parent


def replace_once(path,old,new):
    p=ROOT/path
    text=p.read_text(encoding='utf-8')
    count=text.count(old)
    if count!=1:
        raise SystemExit(f'{path}: expected one match, got {count}')
    p.write_text(text.replace(old,new,1),encoding='utf-8')


def regex_once(path,pattern,replacement):
    p=ROOT/path
    text=p.read_text(encoding='utf-8')
    new,count=re.subn(pattern,replacement,text,count=1,flags=re.S)
    if count!=1:
        raise SystemExit(f'{path}: expected one regex match, got {count}')
    p.write_text(new,encoding='utf-8')


replace_once(
    'graded_photo_multi_source.py',
    'from grading_cert_verifier import lookup_url, verify_cert\n',
    'from grading_cert_verifier import lookup_url\n',
)

new_function=r'''def _official_verify_rows(rows:list[dict],registry:dict,max_live:int=0)->tuple[list[dict],dict]:
 # v194: manual-only means the collector cannot call grader certification sites.
 # Only a persisted manual-verified registry entry may set official_result=True.
 # max_live remains only for call-site compatibility and is intentionally ignored.
 _=max_live
 stats={'registry_matches':0,'live_attempts':0,'live_verified':0,'conflicts':0,'unavailable':0,
        'deferred_by_cooldown':0,'company_deferred':{company:0 for company in COMPANIES},
        'next_retry_seconds':None,
        'company_live_attempts':{company:0 for company in COMPANIES},
        'game_live_attempts':{game:0 for game in GAMES}}
 output=[]
 for raw in rows:
  item=dict(raw)
  company=str(item.get('company') or '').upper()
  cert=normalize_cert(item.get('certification_id'))
  try:grade=float(item.get('grade')) if item.get('grade') is not None else None
  except (TypeError,ValueError,OverflowError):grade=None

  # Stale automatic-verification flags from older candidate/cache generations
  # must never survive the manual-only policy boundary.
  item['official_result']=False
  item['verification_method']=None
  item.pop('official_grade',None)
  item.pop('official_lookup_status',None)
  item['official_lookup_suppressed']=True
  item['automatic_official_lookup_used']=False

  if company not in COMPANIES or not cert or grade is None:
   item['manual_official_verification_required']=True
   item['official_verification']='manual_verification_required'
   output.append(item)
   continue

  item['certification_id']=cert
  item['official_reference_url']=lookup_url(company,cert)
  registered=registry.get((company,cert))
  if registered is not None:
   if abs(float(registered)-grade)<1e-9:
    item.update({'official_result':True,
                 'verification_method':'persisted_manual_verified_registry',
                 'official_verification':'validated_manual_registry',
                 'official_grade':float(registered),
                 'manual_official_verification_required':False})
    stats['registry_matches']+=1
   else:
    item['evidence_conflicts']=sorted(set((item.get('evidence_conflicts') or [])+['official_grade_conflict']))
    item['official_grade']=float(registered)
    item['official_verification']='manual_registry_grade_conflict'
    item['manual_official_verification_required']=True
    stats['conflicts']+=1
  else:
   item['official_verification']='manual_verification_required'
   item['manual_official_verification_required']=True
  output.append(item)

 # Keep the legacy cache file structurally valid but deliberately empty so no
 # previous automatic response can be reused after a restart or upgrade.
 atomic_write_json(OFFICIAL_CACHE,{'schema_version':2,'updated_at':_now(),'entries':{}},suffix='.official-cache.tmp')
 return output,stats
'''

regex_once(
    'graded_photo_multi_source.py',
    r'def _official_verify_rows\(rows:list\[dict\],registry:dict,max_live:int=10\)->tuple\[list\[dict\],dict\]:\n.*?\n(?=def _resolve_cert_conflicts)',
    new_function+'\n',
)

old_test='''    def test_candidate_collection_makes_zero_live_cert_requests(self):\n        rows=[{'company':'BRG','game':'pokemon','grade':10.0,'certification_id':'0346643'}]\n        with mock.patch.object(gp,'verify_cert') as live, \\\n             mock.patch.object(gp,'_load',return_value={}), \\\n             mock.patch.object(gp,'atomic_write_json'):\n            _rows,stats=gp._official_verify_rows(rows,{},max_live=10)\n        live.assert_not_called()\n        self.assertEqual(int(stats.get('live_attempts') or 0),0)\n\n'''
new_test='''    def test_candidate_collection_has_no_live_cert_path_and_scrubs_stale_trust(self):\n        rows=[{'company':'BRG','game':'pokemon','grade':10.0,'certification_id':'0346643',\n               'official_result':True,'verification_method':'live_official_lookup','official_grade':10.0}]\n        with mock.patch.object(gp,'atomic_write_json'):\n            out,stats=gp._official_verify_rows(rows,{},max_live=10)\n        source=inspect.getsource(gp._official_verify_rows)\n        self.assertNotIn('verify_cert(',source)\n        self.assertFalse(out[0].get('official_result'),out[0])\n        self.assertTrue(out[0].get('manual_official_verification_required'),out[0])\n        self.assertEqual(out[0].get('official_verification'),'manual_verification_required')\n        self.assertEqual(int(stats.get('live_attempts') or 0),0)\n\n    def test_manual_verified_registry_is_the_only_collector_promotion(self):\n        rows=[{'company':'BRG','game':'pokemon','grade':10.0,'certification_id':'0346643'}]\n        with mock.patch.object(gp,'atomic_write_json'):\n            out,stats=gp._official_verify_rows(rows,{('BRG','0346643'):10.0},max_live=99)\n        self.assertTrue(out[0].get('official_result'),out[0])\n        self.assertEqual(out[0].get('verification_method'),'persisted_manual_verified_registry')\n        self.assertFalse(out[0].get('manual_official_verification_required'),out[0])\n        self.assertEqual(int(stats.get('registry_matches') or 0),1)\n\n'''
replace_once('test_manual_only_official_verification_v192.py',old_test,new_test)

print('[OK] manual-only collector hardening v194 applied')

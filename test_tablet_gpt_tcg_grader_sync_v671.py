"""V671 immutable review of historical V661 and V669 tests."""
import hashlib
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
import sync_v376_successor_test_support as historic
from execution.tests.test_ai_score_freshness_v270 import AIScoreFreshnessV270Tests

ROOT=Path(__file__).resolve().parent
CONTRACT="TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V671.json"
BASE="d64f5dec3827485d4817fbc2c0c84f8a9f62cde7"
CANDIDATE="91fec3ebfcec5a6fa7f618e0240c29b2dce8e4ba"
WATCHED="execution/tests/test_image_autonomy_v661.py"
OTHER="test_tablet_gpt_tcg_grader_sync_v669.py"

def load(path):
    p=ROOT/path
    if not p.is_file() or p.is_symlink():raise AssertionError('unsafe:'+path)
    return json.loads(p.read_text(encoding="utf-8"))

def digest(rows):
    return hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False,separators=(",",":")).encode("utf-8")).hexdigest()

class V671LegacyFixtureSync(unittest.TestCase):
    def test_previous_approvals_and_current_bytes(self):
        historic.assert_v671_legacy_fixture_successor(self)
        historic.assert_v662_successor(self)
        historic.assert_v670_model_snapshot_successor(self)
        self.assertFalse(historic.V671_LEGACY_PROOF['deployment_allowed'])

    def test_exact_lesson_chain_and_candidate(self):
        c=load(CONTRACT);p=load(c['prior_contract']);d=load(c['delta_snapshot'])
        old=load(c['prior_delta_snapshot']);r=load(c['receiver_receipt']);x=c['candidate_sync']
        self.assertEqual(c['current_required_lesson_count'],161)
        self.assertEqual(c['prior_required_lesson_count'],p['current_required_lesson_count'])
        self.assertEqual(c['delta_required_lesson_count'],len(d['lessons']))
        self.assertEqual(c['current_required_lesson_count'],p['current_required_lesson_count']+len(d['lessons']))
        self.assertEqual(c['rules'],p['rules'])
        for key in ('exact_paths','path_prefixes','exclude_paths'):
            self.assertTrue(set(p['freshness_watch'][key])<=set(c['freshness_watch'][key]))
        self.assertEqual(digest(d['lessons']),d['lesson_digest_sha256'])
        self.assertEqual(d['lesson_digest_sha256'],r['delta_lesson_digest_sha256'])
        self.assertEqual(old['lesson_digest_sha256'],d['prior_lesson_digest_sha256'])
        self.assertEqual(r['prior_lesson_digest_sha256'],old['lesson_digest_sha256'])
        self.assertEqual(r['status'],'SYNCED_VERIFIED')
        self.assertEqual(r['verification']['contract_version'],'v671')
        self.assertEqual(r['verification']['verification_test'],c['verification_test'])
        self.assertEqual(r['accepted_lesson_ids'],[v['lesson_id'] for v in d['lessons']])
        self.assertEqual(r['source_snapshots'],[c['delta_snapshot']])
        self.assertFalse(r['verification']['physical_tablet_runtime_verified'])
        self.assertFalse(r['verification']['physical_drive_readback_verified'])
        self.assertFalse(c['share_policy']['physical_tablet_runtime_verified'])
        self.assertEqual(x['base_main_sha'],BASE)
        self.assertEqual(x['candidate_commit'],CANDIDATE)
        self.assertEqual(x['watched_paths'],[WATCHED])
        self.assertTrue(x['requires_exact_watched_path_match'])
        self.assertTrue(x['post_merge_coverage_allowed'])
        self.assertEqual(set(x['generation_files']),set([CONTRACT,c['delta_snapshot'],c['receiver_receipt'],c['verification_test']]))
        self.assertTrue(set(x['generation_files'])<=set(c['freshness_watch']['exclude_paths']))
        subprocess.run(['git','merge-base','--is-ancestor',BASE,CANDIDATE],cwd=ROOT,check=True)
        subprocess.run(['git','merge-base','--is-ancestor',CANDIDATE,'HEAD'],cwd=ROOT,check=True)
        changed=set(subprocess.check_output(['git','diff','--name-only','--no-renames',BASE,CANDIDATE],cwd=ROOT,text=True).splitlines())
        self.assertEqual(changed,{WATCHED,OTHER,'integrity_manifest.json'})
        fw=c['freshness_watch'];selected=sorted(p for p in changed if p not in fw['exclude_paths'] and (p in fw['exact_paths'] or any(p.startswith(x) for x in fw['path_prefixes'])))
        self.assertEqual(selected,[WATCHED])

    def test_tamper_rejected(self):
        original=Path.read_bytes
        for name in (WATCHED,OTHER):
            with self.subTest(name=name):
                target=ROOT/name
                with patch.object(Path,'read_bytes',lambda p: original(p)+b' #invalid' if p==target else original(p)):
                    with self.assertRaises(AssertionError):historic.assert_v671_legacy_fixture_successor(self)

    def test_relocated_ai_freshness_exact_bytes(self):
        current=ROOT/'execution/tests/test_ai_score_freshness_v270.py'
        self.assertTrue(current.is_file())
        self.assertFalse(current.is_symlink())
        self.assertFalse((ROOT/'test_ai_score_freshness_v270.py').exists())
        self.assertEqual(subprocess.check_output(['git','show',BASE+':test_ai_score_freshness_v270.py'],cwd=ROOT),current.read_bytes())

if __name__=='__main__':unittest.main()

"""V669 formal generation, source-only and no physical runtime claims."""
from __future__ import annotations
import hashlib
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import sync_v376_successor_test_support as historic
from execution.tests.test_cgc_reviewed_scope_v563 import ReviewedCgcScopeV563  # root regression retained

ROOT=Path(__file__).resolve().parent
CONTRACT="TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V669.json"
MODEL="execution/tablet_image_model_gate.py"
CANDIDATE="6da98f94a4d6c817678db6d68dad0eecef82e791"
BASE="172dddb0c7f3100a8f12b8811ae84558e5ce8f26"

def read(path):
    p=ROOT/path
    if p.is_symlink() or not p.is_file():raise AssertionError('MISSING_OR_SYMLINK:'+path)
    return json.loads(p.read_text(encoding='utf-8'))

def digest(rows):
    return hashlib.sha256(json.dumps(rows,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf-8')).hexdigest()

class V669FormalSyncTests(unittest.TestCase):
    def test_contract_chain_candidate_scope_and_lesson_digest(self):
        c=read(CONTRACT);prior=read(c['prior_contract'])
        d=read(c['delta_snapshot']);prior_delta=read(c['prior_delta_snapshot']);r=read(c['receiver_receipt'])
        self.assertEqual(c['prior_required_lesson_count'],prior['current_required_lesson_count'])
        self.assertEqual(c['current_required_lesson_count'],159)
        self.assertEqual(c['delta_required_lesson_count'],len(d['lessons']))
        self.assertEqual(c['current_required_lesson_count'],prior['current_required_lesson_count']+len(d['lessons']))
        self.assertEqual(c['rules'],prior['rules'])
        for key in ('exact_paths','path_prefixes','exclude_paths'):
            self.assertTrue(set(prior['freshness_watch'][key])<=set(c['freshness_watch'][key]))
        self.assertEqual(digest(d['lessons']),d['lesson_digest_sha256'])
        self.assertEqual(d['lesson_digest_sha256'],r['delta_lesson_digest_sha256'])
        self.assertEqual(prior_delta['lesson_digest_sha256'],d['prior_lesson_digest_sha256'])
        self.assertEqual(prior_delta['lesson_digest_sha256'],r['prior_lesson_digest_sha256'])
        self.assertEqual(r['accepted_lesson_ids'],[x['lesson_id'] for x in d['lessons']])
        self.assertEqual(r['status'],'SYNCED_VERIFIED')
        self.assertEqual(r['verification']['verification_test'],c['verification_test'])
        self.assertEqual(r['verification']['contract_version'],'v669')
        self.assertEqual(r['source_main_sha'],d['source_main_sha'])
        self.assertEqual(r['source_snapshots'],[c['delta_snapshot']])
        self.assertFalse(r['verification']['physical_tablet_runtime_verified'])
        self.assertFalse(r['verification']['physical_drive_readback_verified'])
        self.assertFalse(d['share_policy']['cloud_upload_enabled'])
        self.assertFalse(d['share_policy']['device_local_runtime_memory_overwritten'])
        self.assertFalse(c['share_policy']['physical_tablet_runtime_verified'])

    def test_pinned_candidate_and_exact_watched_path(self):
        c=read(CONTRACT);x=c['candidate_sync'];fw=c['freshness_watch']
        self.assertEqual(x['base_main_sha'],BASE);self.assertEqual(x['candidate_commit'],CANDIDATE)
        self.assertEqual(x['watched_paths'],[MODEL])
        self.assertTrue(x['requires_exact_watched_path_match'])
        self.assertTrue(x['post_merge_coverage_allowed'])
        self.assertEqual(set(x['generation_files']),set([CONTRACT,c['delta_snapshot'],c['receiver_receipt'],c['verification_test']]))
        self.assertTrue(set(x['generation_files'])<=set(fw['exclude_paths']))
        subprocess.run(['git','merge-base','--is-ancestor',BASE,CANDIDATE],cwd=ROOT,check=True)
        subprocess.run(['git','merge-base','--is-ancestor',CANDIDATE,'HEAD'],cwd=ROOT,check=True)
        changed=subprocess.check_output(['git','diff','--name-only','--no-renames',BASE,CANDIDATE],cwd=ROOT,text=True).splitlines()
        self.assertEqual(set(changed),set([MODEL,'execution/tests/test_tablet_image_model_gate_v669.py','integrity_manifest.json']))
        watched=sorted(x for x in changed if x not in fw['exclude_paths'] and (x in fw['exact_paths'] or any(x.startswith(p) for p in fw['path_prefixes'])))
        self.assertEqual(watched,x['watched_paths'])
        self.assertEqual("",subprocess.check_output(['git','diff','--name-only','--no-renames',CANDIDATE,'HEAD','--',MODEL],cwd=ROOT,text=True).strip())

    def test_source_only_gate_proof_and_historical_v661(self):
        historic.assert_v669_model_gate_successor(self)
        historic.assert_v661_successor(self)
        self.assertFalse(historic.V661_PROOF['deployment_allowed'])
        self.assertFalse(historic.V669_GATE_PROOF['deployment_allowed'])

    def test_tampered_model_cannot_hide_watched_path(self):
        orig=Path.read_bytes
        def altered(p):
            payload=orig(p)
            return payload+b" #unreviewed" if p==ROOT/MODEL else payload
        with patch.object(Path,'read_bytes',altered):
            with self.assertRaises(AssertionError):
                historic.assert_v669_model_gate_successor(self)

    def test_preserve_previous_regression_bytes(self):
        historical=ROOT/'execution/tests/test_cgc_reviewed_scope_v563.py'
        self.assertTrue(historical.is_file())
        self.assertFalse(historical.is_symlink())
        self.assertFalse((ROOT/'test_cgc_reviewed_scope_v563.py').exists())

if __name__=='__main__':
    unittest.main()

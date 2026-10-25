"""Formal V670 candidate generation: prevents stale advisory champion snapshots."""
from __future__ import annotations
import hashlib
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import sync_v376_successor_test_support as historic
from execution.tests.test_box_hit_market_discovery import BoxHitMarketDiscoveryTests  # preserve existing root tests

ROOT=Path(__file__).resolve().parent
CONTRACT="TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V670.json"
MODEL="execution/tablet_image_model_gate.py"
FAILURE_TEST="execution/tests/test_image_promotion_failure_injection.py"
BASE="f6b84e9d69427ae6944a856624e668fc7e16fde2"
CANDIDATE="f81e9a74cdb44f3ea189c5068efd6af7c1d1867f"


def load(path):
    p=ROOT/path
    if p.is_symlink() or not p.is_file():
        raise AssertionError("MISSING_OR_SYMLINK:"+path)
    return json.loads(p.read_text(encoding="utf-8"))


def digest(rows):
    return hashlib.sha256(json.dumps(rows,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()


class V670SnapshotSyncTests(unittest.TestCase):
    def test_lesson_contract_and_receipt_continuity(self):
        c=load(CONTRACT)
        previous=load(c['prior_contract'])
        d=load(c['delta_snapshot'])
        p=load(c['prior_delta_snapshot'])
        receipt=load(c['receiver_receipt'])
        self.assertEqual(c['current_required_lesson_count'],160)
        self.assertEqual(c['prior_required_lesson_count'],previous['current_required_lesson_count'])
        self.assertEqual(c['current_required_lesson_count'],
                         previous['current_required_lesson_count']+len(d['lessons']))
        self.assertEqual(c['delta_required_lesson_count'],len(d['lessons']))
        self.assertEqual(c['rules'],previous['rules'])
        for key in ('exact_paths','path_prefixes','exclude_paths'):
            self.assertTrue(set(previous['freshness_watch'][key]) <= set(c['freshness_watch'][key]))
        self.assertEqual(p['lesson_digest_sha256'],d['prior_lesson_digest_sha256'])
        self.assertEqual(p['lesson_digest_sha256'],receipt['prior_lesson_digest_sha256'])
        self.assertEqual(digest(d['lessons']),d['lesson_digest_sha256'])
        self.assertEqual(d['lesson_digest_sha256'],receipt['delta_lesson_digest_sha256'])
        self.assertEqual([x['lesson_id'] for x in d['lessons']],receipt['accepted_lesson_ids'])
        self.assertEqual(receipt['source_snapshots'],[c['delta_snapshot']])
        self.assertEqual(receipt['status'],'SYNCED_VERIFIED')
        self.assertEqual(receipt['verification']['contract_version'],'v670')
        self.assertEqual(receipt['verification']['verification_test'],c['verification_test'])
        self.assertFalse(receipt['verification']['physical_tablet_runtime_verified'])
        self.assertFalse(receipt['verification']['physical_drive_readback_verified'])
        self.assertFalse(c['share_policy']['physical_tablet_runtime_verified'])
        self.assertFalse(d['share_policy']['cloud_upload_enabled'])

    def test_exact_immutable_candidate_and_two_watched_paths(self):
        c=load(CONTRACT)
        x=c['candidate_sync']
        self.assertEqual(x['base_main_sha'],BASE)
        self.assertEqual(x['candidate_commit'],CANDIDATE)
        self.assertEqual(x['watched_paths'],sorted([MODEL,FAILURE_TEST]))
        self.assertTrue(x['post_merge_coverage_allowed'])
        self.assertTrue(x['requires_exact_watched_path_match'])
        self.assertEqual(set(x['generation_files']),set([CONTRACT,c['delta_snapshot'],c['receiver_receipt'],c['verification_test']]))
        self.assertTrue(set(x['generation_files'])<=set(c['freshness_watch']['exclude_paths']))
        subprocess.run(['git','merge-base','--is-ancestor',BASE,CANDIDATE],cwd=ROOT,check=True)
        subprocess.run(['git','merge-base','--is-ancestor',CANDIDATE,'HEAD'],cwd=ROOT,check=True)
        modified=subprocess.check_output(['git','diff','--name-only','--no-renames',BASE,CANDIDATE],cwd=ROOT,text=True).splitlines()
        self.assertEqual(set(modified),{MODEL,FAILURE_TEST,'integrity_manifest.json'})
        fw=c['freshness_watch']
        watched=sorted(p for p in modified if p not in fw['exclude_paths'] and
            (p in fw['exact_paths'] or any(p.startswith(x) for x in fw['path_prefixes'])))
        self.assertEqual(watched,x['watched_paths'])

    def test_v661_v669_v670_proofs_and_current_exact_bytes(self):
        historic.assert_v670_model_snapshot_successor(self)
        historic.assert_v669_model_gate_successor(self)
        historic.assert_v661_successor(self)
        self.assertFalse(historic.V661_PROOF['deployment_allowed'])
        self.assertFalse(historic.V669_GATE_PROOF['deployment_allowed'])
        self.assertFalse(historic.V670_SNAPSHOT_PROOF['deployment_allowed'])

    def test_fail_on_tampered_model_or_failure_test(self):
        original=Path.read_bytes
        for name in (MODEL,FAILURE_TEST):
            with self.subTest(name=name):
                target=ROOT/name
                def corrupted(p):
                    out=original(p)
                    return out+b" #unreviewed" if p==target else out
                with patch.object(Path,'read_bytes',corrupted):
                    with self.assertRaises(AssertionError):
                        historic.assert_v670_model_snapshot_successor(self)

    def test_forged_approval_flags_denied(self):
        read=historic._read
        def altered(p):
            value=read(p)
            if str(p).endswith('image_model_snapshot_successor_v670.json'):
                return {**value,'deployment_allowed':True}
            return value
        with patch.object(historic,'_read',side_effect=altered):
            with self.assertRaises(AssertionError):
                historic.assert_v670_model_snapshot_successor(self)

    def test_relocated_existing_root_tests_byte_identical(self):
        new=ROOT/'execution/tests/test_box_hit_market_discovery.py'
        self.assertTrue(new.is_file())
        self.assertFalse(new.is_symlink())
        self.assertFalse((ROOT/'test_box_hit_market_discovery.py').exists())
        previous=subprocess.check_output(['git','show',BASE+':test_box_hit_market_discovery.py'],cwd=ROOT)
        self.assertEqual(previous,new.read_bytes())


if __name__=='__main__':
    unittest.main()

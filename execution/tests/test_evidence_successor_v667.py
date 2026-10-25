import hashlib,json,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
import sync_v376_successor_test_support as sync

class ImageSuccessorTests(unittest.TestCase):
    def test_exact_source_and_old_learning_gate(self):
        sync.assert_v667_successor(self);sync.assert_v645_feature_successor(self);sync.assert_v652_successor(self);sync.assert_v653_successor(self)

    def test_live_bytes_never_hidden_after_cache_warmup(self):
        sync.assert_v667_successor(self);original=Path.read_bytes
        for name,digest in sync.V667_PROOF['reviewed_sha256'].items():
            if digest is None:continue
            with self.subTest(path=name),patch.object(Path,'read_bytes',lambda p:original(p)+b' unreviewed' if p==sync.ROOT/name else original(p)):
                with self.assertRaises(AssertionError):sync.assert_v667_successor(self)
                self.assertEqual([name],sync.preserve_reviewed_v667_scope([name],sync.V667_PROOF['base_commit']))

    def test_contract_preserves_rules_and_exact_candidate(self):
        c=json.loads((sync.ROOT/'TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V667.json').read_text())
        old=json.loads((sync.ROOT/c['prior_contract']).read_text())
        self.assertEqual(old['rules'],c['rules']);self.assertEqual(sync.V667_PROOF['candidate_commit'],c['candidate_sync']['candidate_commit'])
        d=json.loads((sync.ROOT/c['delta_snapshot']).read_text());r=json.loads((sync.ROOT/c['receiver_receipt']).read_text())
        digest=hashlib.sha256(json.dumps(d['lessons'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(digest,d['lesson_digest_sha256']);self.assertEqual(digest,r['delta_lesson_digest_sha256'])
        self.assertEqual(old['current_required_lesson_count']+1,c['current_required_lesson_count'])
        self.assertFalse(r['verification']['physical_tablet_runtime_verified'])
        names=subprocess.check_output(['git','diff','--name-only','--no-renames',sync.V667_PROOF['base_commit'],sync.V667_PROOF['candidate_commit']],cwd=sync.ROOT,text=True).splitlines()
        w=c['freshness_watch'];actual=sorted(p for p in names if p not in w['exclude_paths'] and (p in w['exact_paths'] or p.startswith(tuple(w['path_prefixes']))))
        self.assertEqual(actual,c['candidate_sync']['watched_paths'])

    def test_relocated_loader_is_byte_identical_and_root_budget_preserved(self):
        name='test_manual_registration_delete_v151.py'
        before=subprocess.check_output(['git','show',sync.V667_PROOF['base_commit']+':'+name],cwd=sync.ROOT)
        self.assertFalse((sync.ROOT/name).exists())
        self.assertEqual(before,(sync.ROOT/'execution/tests'/name).read_bytes())
        self.assertIn('execution.tests.test_manual_registration_delete_v151',(sync.ROOT/'test_tablet_gpt_tcg_grader_sync_v667.py').read_text())
        def count(ref):return len([x for x in subprocess.check_output(['git','ls-tree','-z',ref],cwd=sync.ROOT).split(b'\0') if x])
        self.assertLessEqual(count('HEAD'),count('328782f6b92835c4aab39224bb0c6c5c6b3e0067'))

"""V673 immutable malformed-input fix; preserve existing numeric regression cases."""
import hashlib
import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import sync_v376_successor_test_support as historic
from execution.tests.test_runtime_learning_math_neural_v278 import RuntimeLearningMathNeuralV278Tests
from execution.tests.test_tablet_image_model_gate_v673 import ImageGateInvalidInputRejection

ROOT = Path(__file__).resolve().parent
CONTRACT = 'TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V673.json'
BASE = '17001bab74ff862fa488ed65792d545d5b68e261'
CANDIDATE = '3973ca5baf1bcd1a90d1a7717ca3af268efa2860'
MODEL = 'execution/tablet_image_model_gate.py'
BEHAVIOR_TEST = 'execution/tests/test_tablet_image_model_gate_v673.py'
RELOCATED_TEST = 'test_runtime_learning_math_neural_v278.py'


def load(relative):
    path = ROOT / relative
    if path.is_symlink() or not path.is_file():
        raise AssertionError('unsafe_or_missing:' + relative)
    return json.loads(path.read_text(encoding='utf-8'))


class V673InputTotalitySyncTests(unittest.TestCase):
    def test_lesson_contract_receipt_and_existing_policy_continuity(self):
        contract = load(CONTRACT)
        previous = load(contract['prior_contract'])
        delta = load(contract['delta_snapshot'])
        prior = load(contract['prior_delta_snapshot'])
        receipt = load(contract['receiver_receipt'])
        digest = hashlib.sha256(json.dumps(delta['lessons'], ensure_ascii=False,
            sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(contract['current_required_lesson_count'], 162)
        self.assertEqual(contract['prior_required_lesson_count'], previous['current_required_lesson_count'])
        self.assertEqual(contract['delta_required_lesson_count'], len(delta['lessons']))
        self.assertEqual(contract['current_required_lesson_count'],
                         previous['current_required_lesson_count'] + len(delta['lessons']))
        self.assertEqual(contract['rules'], previous['rules'])
        for key in ('exact_paths', 'path_prefixes', 'exclude_paths'):
            self.assertLessEqual(set(previous['freshness_watch'][key]), set(contract['freshness_watch'][key]))
        self.assertEqual(prior['lesson_digest_sha256'], delta['prior_lesson_digest_sha256'])
        self.assertEqual(prior['lesson_digest_sha256'], receipt['prior_lesson_digest_sha256'])
        self.assertEqual(digest, delta['lesson_digest_sha256'])
        self.assertEqual(digest, receipt['delta_lesson_digest_sha256'])
        self.assertEqual(receipt['accepted_lesson_ids'], [v['lesson_id'] for v in delta['lessons']])
        self.assertEqual(receipt['source_snapshots'], [contract['delta_snapshot']])
        self.assertEqual(receipt['status'], 'SYNCED_VERIFIED')
        self.assertEqual(receipt['verification']['contract_version'], 'v673')
        self.assertEqual(receipt['verification']['verification_test'], contract['verification_test'])
        self.assertEqual(delta['source_main_sha'], BASE)
        self.assertEqual(receipt['source_main_sha'], BASE)
        self.assertFalse(receipt['verification']['physical_tablet_runtime_verified'])
        self.assertFalse(receipt['verification']['physical_drive_readback_verified'])
        self.assertFalse(contract['share_policy']['physical_tablet_runtime_verified'])
        self.assertFalse(delta['share_policy']['cloud_upload_enabled'])

    def test_exact_frozen_candidate_scope_and_ancestry(self):
        contract = load(CONTRACT)
        candidate = contract['candidate_sync']
        self.assertEqual(candidate['base_main_sha'], BASE)
        self.assertEqual(candidate['candidate_commit'], CANDIDATE)
        self.assertEqual(candidate['watched_paths'], [MODEL, BEHAVIOR_TEST])
        self.assertTrue(candidate['post_merge_coverage_allowed'])
        self.assertTrue(candidate['requires_exact_watched_path_match'])
        generations = {CONTRACT, contract['delta_snapshot'], contract['receiver_receipt'], contract['verification_test']}
        self.assertEqual(set(candidate['generation_files']), generations)
        self.assertLessEqual(generations, set(contract['freshness_watch']['exclude_paths']))
        subprocess.run(['git', 'merge-base', '--is-ancestor', BASE, CANDIDATE], cwd=ROOT, check=True)
        subprocess.run(['git', 'merge-base', '--is-ancestor', CANDIDATE, 'HEAD'], cwd=ROOT, check=True)
        changed = set(subprocess.check_output(['git', 'diff', '--name-only', '--no-renames', BASE, CANDIDATE], cwd=ROOT, text=True).splitlines())
        self.assertEqual(changed, {MODEL, BEHAVIOR_TEST, 'integrity_manifest.json'})
        watch = contract['freshness_watch']
        selected = sorted(p for p in changed if p not in watch['exclude_paths'] and
                          (p in watch['exact_paths'] or any(p.startswith(x) for x in watch['path_prefixes'])))
        self.assertEqual(selected, candidate['watched_paths'])

    def test_previous_proofs_remain_pinned_and_current_bytes_match(self):
        historic.assert_v673_model_input_successor(self)
        historic.assert_v670_model_snapshot_successor(self)
        historic.assert_v669_model_gate_successor(self)
        historic.assert_v661_successor(self)
        self.assertEqual(historic.V673_INPUT_PROOF['baseline_sha256'][MODEL],
                         historic.V670_SNAPSHOT_PROOF['reviewed_sha256'][MODEL])

    def test_warm_cache_never_hides_changed_model_or_test_bytes(self):
        historic.assert_v673_model_input_successor(self)
        original = Path.read_bytes
        for name in (MODEL, BEHAVIOR_TEST):
            target = ROOT / name
            with self.subTest(name=name), patch.object(Path, 'read_bytes',
                    lambda path: original(path) + b' #unreviewed' if path == target else original(path)):
                with self.assertRaises(AssertionError):
                    historic.assert_v673_model_input_successor(self)

    def test_forged_device_or_model_approval_rejected(self):
        original = historic._read
        evidence = ROOT / '.github/tablet-autonomy/image_model_input_successor_v673.json'
        for key in ('deployment_allowed', 'physical_tablet_runtime_verified', 'model_promotion_allowed'):
            with self.subTest(key=key), patch.object(historic, '_read',
                    side_effect=lambda path: {**original(path), key: True} if path == evidence else original(path)):
                with self.assertRaises(AssertionError):
                    historic.assert_v673_model_input_successor(self)

    def test_existing_numeric_tests_relocated_byte_identically(self):
        path = ROOT / 'execution/tests' / RELOCATED_TEST
        self.assertFalse(path.is_symlink())
        self.assertFalse((ROOT / RELOCATED_TEST).exists())
        original = subprocess.check_output(['git', 'show', BASE + ':' + RELOCATED_TEST], cwd=ROOT)
        self.assertEqual(path.read_bytes(), original)


def load_tests(loader, _standard_tests, _pattern):
    # Register the imported behavioral suites explicitly, including all three
    # byte-preserved numeric cases; keep discovery and direct invocation equal.
    suite = unittest.TestSuite()
    for case in (RuntimeLearningMathNeuralV278Tests, ImageGateInvalidInputRejection,
                 V673InputTotalitySyncTests):
        suite.addTests(loader.loadTestsFromTestCase(case))
    return suite


if __name__ == '__main__':
    unittest.main()

"""TCG main P0 regression probes. Tests run with temporary files only."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import ai_performance_runtime as performance
import tcg_updater as updater


class VerificationTypeGateTests(unittest.TestCase):
    def _observe(self, verified, verification=None, regression_pass=True):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            event = {"path": "collector.py", "message": "verified fix",
                     "changed_files": ["collector.py"], "verified": verified,
                     "regression_pass": regression_pass}
            if verification is not None:
                event["verification"] = verification
            result = performance.observe([event], state_path=root / "state.json",
                                         code_map_root=root, dry_run=True)
            return result['summary']['verified_code_map_learning']

    def test_false_like_or_non_boolean_is_not_evidence(self):
        for v in ('false', 'False', '0', 'true', 1, ['verified'], {'state':'approved'}, False, None):
            with self.subTest(value=repr(v)):
                self.assertEqual(self._observe(v), 0)

    def test_actual_boolean_true_with_regression_is_eligible(self):
        self.assertEqual(self._observe(True), 1)
        self.assertEqual(self._observe(True, regression_pass=False), 0)

    def test_legacy_status_literals_remain_exact_and_bounded(self):
        self.assertEqual(self._observe(False, 'verified'), 1)
        self.assertEqual(self._observe(False, 'full_regression_verified'), 1)
        self.assertEqual(self._observe(False, 'not_verified'), 0)
        self.assertEqual(self._observe(False, ['verified']), 0)


class LearningStorePreservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'learning_store.json'
        self.patcher = mock.patch.object(updater, 'LEARNING_STORE', str(self.path));self.patcher.start();self.addCleanup(self.patcher.stop)
        updater.clear_json_file_cache();self.addCleanup(updater.clear_json_file_cache)

    def _post(self, incoming):
        handler = updater.Handler.__new__(updater.Handler)
        handler.path = '/api/learning-store'
        handler._require_request_host = lambda: True
        handler._require_mutation_origin = lambda: True
        handler._read_json_body = lambda _: incoming
        handler.json = lambda payload, status=200: (payload, status)
        with mock.patch('vision_calibration.train_file', return_value={'profiles':{}}), \
             mock.patch('grading_accuracy_v99.sanitize_rows', return_value=[]), \
             mock.patch('grading_accuracy_v99.train_company_calibration', return_value={}):
            return updater.Handler.do_POST(handler)

    def test_confirmed_samples_and_future_metadata_survive_api_save(self):
        preserved = {
            'version':3, 'updated_at':'old', 'v99_validation': [], 'v30_validation': [], 'v11_validation': [],
            'confirmed_samples':[{'company':'BGS','verified': True, 'certification_id':'ABC001', 'actual':9.5}],
            'calibration': {'preserve':True}, 'bgs_subgrade_summary':{'observed':11},
            'future_extension': {'raw_verified_evidence':[1,2,3]},
        }
        self.path.write_text(json.dumps(preserved),encoding='utf-8')
        reply, status = self._post({'v99_validation': []})
        self.assertEqual(status, 200,reply)
        saved=json.loads(self.path.read_text(encoding='utf-8'))
        for k in ('confirmed_samples','calibration','bgs_subgrade_summary','future_extension'):
            self.assertEqual(saved[k],preserved[k])
        self.assertGreaterEqual(saved['version'],3)
        self.assertTrue((Path(str(self.path)+'.bak')).exists())

    def test_client_cannot_inject_unverified_top_level_evidence(self):
        self.path.write_text(json.dumps({'version':2,'confirmed_samples':[{'existing':True}]}),encoding='utf-8')
        _,status=self._post({'confirmed_samples':[{'attacker':True}], 'future_extension':{'new':'untrusted'}})
        self.assertEqual(status,200)
        data=json.loads(self.path.read_text(encoding='utf-8'))
        self.assertEqual(data['confirmed_samples'],[{'existing':True}])
        self.assertNotIn('future_extension',data)

    def test_damaged_original_is_not_overwritten(self):
        self.path.write_text('{broken',encoding='utf-8')
        _,status = self._post({'v99_validation':[]})
        self.assertEqual(status,400)
        self.assertEqual(self.path.read_text(encoding='utf-8'), '{broken')

    def test_non_mapping_client_body_cannot_overwrite_state(self):
        original = '{"version": 2, "confirmed_samples": [{"safe": true}]}'
        self.path.write_text(original, encoding='utf-8')
        _, status = self._post([{'v99_validation': []}])
        self.assertEqual(status, 400)
        self.assertEqual(self.path.read_text(encoding='utf-8'), original)

    def test_legacy_v2_empty_save_still_succeeds(self):
        self.path.write_text(json.dumps({'version':2, 'v99_validation':[]}),encoding='utf-8')
        _,status = self._post({'v99_validation':[]})
        self.assertEqual(status,200)

if __name__=='__main__':unittest.main()

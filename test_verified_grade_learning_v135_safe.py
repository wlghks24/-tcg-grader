#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import verified_grade_learning_v135 as base
import verified_grade_learning_v135_safe as safe


class VerifiedGradeLearningV135SafeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.originals = {
            'ROOT': base.ROOT,
            'LEARNING_STORE': base.LEARNING_STORE,
            'VERIFIED_CERTS': base.VERIFIED_CERTS,
            'VISION_CALIBRATION': base.VISION_CALIBRATION,
        }
        base.ROOT = root
        base.LEARNING_STORE = root / 'learning_store.json'
        base.VERIFIED_CERTS = root / 'verified_certifications.json'
        base.VISION_CALIBRATION = root / 'vision_calibration.json'
        # Adapter functions delegate to base; update exported path aliases used by wrapper.
        safe.ROOT = base.ROOT
        safe.LEARNING_STORE = base.LEARNING_STORE
        safe.VERIFIED_CERTS = base.VERIFIED_CERTS
        safe.VISION_CALIBRATION = base.VISION_CALIBRATION

    def tearDown(self):
        for key, value in self.originals.items():
            setattr(base, key, value)
        safe.ROOT = base.ROOT
        safe.LEARNING_STORE = base.LEARNING_STORE
        safe.VERIFIED_CERTS = base.VERIFIED_CERTS
        safe.VISION_CALIBRATION = base.VISION_CALIBRATION
        self.temp.cleanup()

    def test_old_unmarked_vision_profiles_are_never_served(self):
        base.VISION_CALIBRATION.write_text(json.dumps({
            'version': 2,
            'profiles': {'PSA|centered|surface-low|multi': {'enabled': True, 'correction': -1}},
        }), encoding='utf-8')
        status = safe.model_status()
        self.assertEqual(status['vision_profiles'], {})
        self.assertTrue(status['policy']['vision_residual_registry_gate_required'])
        self.assertTrue(status['policy']['cross_process_training_transaction_lock'])
        self.assertTrue(status['policy']['reentrant_learning_transaction_lock'])
        self.assertTrue(status['policy']['proxy_learning_genuine_raw_priority_atomic'])
        self.assertTrue(status['policy']['persisted_version_metadata_repaired'])

    def test_safe_rebuild_marks_registry_gate(self):
        base.VERIFIED_CERTS.write_text(json.dumps({'version': 1, 'certifications': []}), encoding='utf-8')
        base.LEARNING_STORE.write_text(json.dumps({'version': 3, 'v99_validation': []}), encoding='utf-8')
        result = safe.rebuild_safe_vision_calibration()
        self.assertTrue(result['registry_gate_v135'])
        saved = json.loads(base.VISION_CALIBRATION.read_text(encoding='utf-8'))
        self.assertTrue(saved['registry_gate_v135'])
        self.assertEqual(saved['registry_verified_training_rows'], 0)

    def test_model_serves_only_marked_profiles(self):
        base.VERIFIED_CERTS.write_text(json.dumps({'version': 1, 'certifications': []}), encoding='utf-8')
        base.LEARNING_STORE.write_text(json.dumps({'version': 3, 'v99_validation': []}), encoding='utf-8')
        base.VISION_CALIBRATION.write_text(json.dumps({
            'registry_gate_v135': True,
            'profiles': {'PSA|centered|surface-low|multi': {'enabled': False, 'correction': 0}},
        }), encoding='utf-8')
        status = safe.model_status()
        self.assertIn('PSA|centered|surface-low|multi', status['vision_profiles'])

    def test_submit_wraps_base_learning_in_process_lock_and_restores_patch(self):
        events = []

        @contextmanager
        def fake_lock(path, **kwargs):
            events.append(('enter', Path(path), dict(kwargs)))
            yield
            events.append(('exit', Path(path), dict(kwargs)))

        import vision_calibration
        original_train = vision_calibration.train_file

        def fake_submit(payload, verifier=None):
            self.assertEqual(events[0][0], 'enter')
            self.assertEqual(events[0][1], base.LEARNING_STORE)
            self.assertIsNot(vision_calibration.train_file, original_train)
            return {'ok': False, 'accepted': False, 'reason': 'test'}

        with mock.patch.object(safe, 'exclusive_file_lock', fake_lock), \
             mock.patch.object(base, 'submit_verified_sample', fake_submit):
            result = safe.submit_verified_sample({'test': True})

        self.assertFalse(result['accepted'])
        self.assertEqual([row[0] for row in events], ['enter', 'exit'])
        self.assertIs(vision_calibration.train_file, original_train)

    def test_nested_learning_transaction_acquires_one_os_lock(self):
        events = []

        @contextmanager
        def fake_lock(path, **kwargs):
            events.append(('enter', Path(path)))
            yield
            events.append(('exit', Path(path)))

        row = {
            'company': 'PSA', 'certification_id': '10000001', 'actual': 9.0,
            'raw_pred': 9.5, 'pred': 9.5, 'mode': 'raw', 'game': 'pokemon',
        }
        with mock.patch.object(safe, 'exclusive_file_lock', fake_lock), \
             mock.patch.object(safe, '_BASE_APPEND_STORE_ROW') as append:
            with safe._learning_transaction():
                safe._append_store_row(row)
        append.assert_called_once_with(row)
        self.assertEqual([event[0] for event in events], ['enter', 'exit'])

    def test_base_writer_used_by_proxy_watcher_is_centrally_patched(self):
        self.assertIs(base._append_store_row, safe._append_store_row)
        self.assertIs(base._persist_verified_cert, safe._persist_verified_cert)

    def test_slab_proxy_cannot_overwrite_same_cert_genuine_raw_without_source_tag(self):
        genuine = {
            'company': 'PSA', 'certification_id': '10000001', 'actual': 9.0,
            'raw_pred': 9.4, 'pred': 9.4, 'mode': 'raw', 'game': 'pokemon',
            # Historical genuine RAW rows intentionally have no source field.
        }
        base.LEARNING_STORE.write_text(json.dumps({
            'version': 3, 'v99_validation': [genuine], 'v30_validation': [], 'v11_validation': [],
        }), encoding='utf-8')
        proxy = {
            **genuine,
            'raw_pred': 8.8,
            'pred': 8.8,
            'source': 'verified_slab_card_roi_v158',
            'proxy_from_verified_slab': True,
        }
        with self.assertRaisesRegex(ValueError, 'genuine raw sample has priority'):
            safe._append_store_row(proxy)
        saved = json.loads(base.LEARNING_STORE.read_text(encoding='utf-8'))
        self.assertEqual(saved['v99_validation'][0]['raw_pred'], 9.4)
        self.assertNotIn('source', saved['v99_validation'][0])

    def test_existing_proxy_row_can_be_refreshed_by_proxy(self):
        old = {
            'company': 'PSA', 'certification_id': '10000001', 'actual': 9.0,
            'raw_pred': 8.7, 'pred': 8.7, 'mode': 'raw', 'game': 'pokemon',
            'source': 'verified_slab_card_roi_v158',
        }
        base.LEARNING_STORE.write_text(json.dumps({
            'version': 3, 'v99_validation': [old], 'v30_validation': [], 'v11_validation': [],
        }), encoding='utf-8')
        refreshed = {**old, 'raw_pred': 8.9, 'pred': 8.9, 'source': 'verified_slab_card_roi_v159'}
        safe._append_store_row(refreshed)
        saved = json.loads(base.LEARNING_STORE.read_text(encoding='utf-8'))
        self.assertEqual(len(saved['v99_validation']), 1)
        self.assertEqual(saved['v99_validation'][0]['raw_pred'], 8.9)
        self.assertEqual(saved['v99_validation'][0]['source'], 'verified_slab_card_roi_v159')

    def test_malformed_persisted_versions_are_repaired_before_verified_writes(self):
        base.VERIFIED_CERTS.write_text(json.dumps({
            'version': 'NaN', 'certifications': [],
        }), encoding='utf-8')
        safe._persist_verified_cert('PSA', '10000001', 9.0, {
            'official_url': 'https://www.psacard.com/cert/10000001/psa',
        })
        registry = json.loads(base.VERIFIED_CERTS.read_text(encoding='utf-8'))
        self.assertIs(type(registry['version']), int)
        self.assertGreaterEqual(registry['version'], 1)

        base.LEARNING_STORE.write_text(json.dumps({
            'version': 'Infinity', 'v99_validation': [], 'v30_validation': [], 'v11_validation': [],
        }), encoding='utf-8')
        safe._append_store_row({
            'company': 'PSA', 'certification_id': '10000001', 'actual': 9.0,
            'raw_pred': 9.5, 'pred': 9.5, 'mode': 'raw', 'game': 'pokemon',
        })
        store = json.loads(base.LEARNING_STORE.read_text(encoding='utf-8'))
        self.assertIs(type(store['version']), int)
        self.assertGreaterEqual(store['version'], 3)
        self.assertEqual(len(store['v99_validation']), 1)


if __name__ == '__main__':
    unittest.main()

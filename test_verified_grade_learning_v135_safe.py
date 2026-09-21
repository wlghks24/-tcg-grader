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


if __name__ == '__main__':
    unittest.main()

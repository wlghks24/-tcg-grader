"""P0: tracker learning must not accept truthy non-boolean verified values.

Runs only on temporary state and synthetic code-map inputs. No live writes.
"""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path

import ai_auto_tracker as canonical
import ai_performance_runtime as fast


class VerifiedRuntimeGateV882Tests(unittest.TestCase):
    def _event(self, **overrides):
        event = {
            'path': 'collector.py',
            'changed_files': ['outside.py'],
            'message': 'repair observation',
            'regression_pass': True,
        }
        event.update(overrides)
        return event

    def _observe(self, event, *, use_canonical=False):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state = root / 'state.json'
            observer = canonical.observe if use_canonical else fast.observe
            result = observer([event], state_path=state, code_map_root=root)
            saved = json.loads(state.read_text(encoding='utf-8'))
            patterns = saved.get('code_map_learning', {}).get('verified_patterns', {})
            return result['summary']['verified_code_map_learning'], len(patterns)

    def test_truthy_non_boolean_flags_never_promote(self):
        for value in ('false', 'true', '0', '1', 'no', 1, ['true'], {'valid': True}):
            with self.subTest(verified=value):
                self.assertEqual((0, 0), self._observe(self._event(verified=value)))

    def test_boolean_true_and_explicit_verification_status_are_supported(self):
        for event in (self._event(verified=True), self._event(verification='verified'),
                      self._event(verification='full_verified'),
                      self._event(verification='full_regression_verified')):
            with self.subTest(event=event):
                self.assertEqual((1, 1), self._observe(event))

    def test_explicit_false_overrides_stale_positive_status(self):
        for value in (False, 'false', 0):
            with self.subTest(flag=value):
                self.assertEqual((0, 0), self._observe(self._event(verified=value, verification='verified')))

    def test_failed_or_pending_marker_cannot_override_boolean_flag(self):
        for status in ('failed', 'pending', 'false', '', 1):
            with self.subTest(status=status):
                self.assertEqual((0, 0), self._observe(self._event(verified=True, verification=status)))

    def test_regression_must_be_exact_boolean_true(self):
        for value in ('true', 1, False, None):
            with self.subTest(regression_pass=value):
                self.assertEqual((0, 0), self._observe(self._event(verified=True, regression_pass=value)))

    def test_canonical_entrypoint_shares_gate(self):
        self.assertEqual((0, 0), self._observe(self._event(verified='false'), use_canonical=True))
        self.assertEqual((1, 1), self._observe(self._event(verified=True), use_canonical=True))


if __name__ == '__main__':
    unittest.main()

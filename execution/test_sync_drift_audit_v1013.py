"""Fail-closed regression checks for the read-only sync drift evidence collector."""
import contextlib
import io
import json
import unittest
from unittest.mock import patch
from execution import sync_drift_audit_v1013 as audit


class SyncDriftAuditTests(unittest.TestCase):
    def test_current_checkout_audit_does_not_approve_deployment(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rc = audit.main()
        report = json.loads(output.getvalue())
        self.assertEqual(rc, 0)
        self.assertTrue(report['audit_complete'])
        self.assertIs(report['sync_successor_approved'], False)
        self.assertIs(report['physical_tablet_verified'], False)
        self.assertEqual(set(audit.PATHS), {row['path'] for row in report['paths']})
        self.assertTrue(any(row['changed_after_v641'] for row in report['paths']))

    def test_missing_history_fails_closed(self):
        original_git = audit.git
        def missing_history(*args):
            if args[:2] == ('merge-base', '--is-ancestor'):
                return type('Result', (), {'returncode': 1, 'stdout': b''})()
            return original_git(*args)
        output = io.StringIO()
        with patch.object(audit, 'git', side_effect=missing_history), contextlib.redirect_stdout(output):
            rc = audit.main()
        report = json.loads(output.getvalue())
        self.assertEqual(rc, 2)
        self.assertFalse(report['audit_complete'])
        self.assertEqual(report['hold_reason'], 'v641_history_missing')
        self.assertFalse(report['sync_successor_approved'])


if __name__ == '__main__':
    unittest.main()

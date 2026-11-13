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

    def test_working_tree_drift_fails_closed(self):
        original_git = audit.git
        def tampered_head(*args):
            if args[:2] == ('show', 'HEAD:' + audit.PATHS[0]):
                return type('Result', (), {'returncode': 0, 'stdout': b'not-current-source'})()
            return original_git(*args)
        output = io.StringIO()
        with patch.object(audit, 'git', side_effect=tampered_head), contextlib.redirect_stdout(output):
            rc = audit.main()
        report = json.loads(output.getvalue())
        self.assertEqual(rc, 2)
        self.assertFalse(report['audit_complete'])
        self.assertEqual(report['hold_reason'], 'working_tree_drift:' + audit.PATHS[0])
        self.assertFalse(report['sync_successor_approved'])

    def test_unexpected_v1013_workflow_history_fails_closed(self):
        original_git = audit.git
        workflow = '.github/workflows/tablet-v1013-offdevice-compare.yml'
        def forged_history(*args):
            if args == ('show', audit.V641_BASE + ':' + workflow):
                return type('Result', (), {'returncode': 0, 'stdout': b'forged-old-workflow'})()
            return original_git(*args)
        output = io.StringIO()
        with patch.object(audit, 'git', side_effect=forged_history), contextlib.redirect_stdout(output):
            rc = audit.main()
        report = json.loads(output.getvalue())
        self.assertEqual(rc, 2)
        self.assertFalse(report['audit_complete'])
        self.assertEqual(report['hold_reason'], 'v1013_workflow_unexpected_history')
        self.assertFalse(report['sync_successor_approved'])

    def test_v641_pinned_bytes_mutation_fails_closed(self):
        original_git = audit.git
        target = audit.PATHS[0]
        def altered_v641(*args):
            if args == ('show', 'HEAD:' + target):
                return original_git(*args)
            if args == ('show', audit.V641_CANDIDATE + ':' + target):
                return type('Result', (), {'returncode': 0, 'stdout': b'altered-v641-history'})()
            return original_git(*args)
        output = io.StringIO()
        with patch.object(audit, 'git', side_effect=altered_v641), contextlib.redirect_stdout(output):
            rc = audit.main()
        report = json.loads(output.getvalue())
        self.assertEqual(rc, 2)
        self.assertFalse(report['audit_complete'])
        self.assertEqual(report['hold_reason'], 'v641_pin_mismatch:' + target)
        self.assertFalse(report['sync_successor_approved'])

    def test_unexpected_git_history_error_fails_closed(self):
        original_git = audit.git
        workflow = '.github/workflows/tablet-v1013-offdevice-compare.yml'
        def broken_history(*args):
            if args == ('show', audit.V641_BASE + ':' + workflow):
                return type('Result', (), {'returncode': 1, 'stdout': b''})()
            return original_git(*args)
        output = io.StringIO()
        with patch.object(audit, 'git', side_effect=broken_history), contextlib.redirect_stdout(output):
            rc = audit.main()
        report = json.loads(output.getvalue())
        self.assertEqual(rc, 2)
        self.assertFalse(report['audit_complete'])
        self.assertEqual(report['hold_reason'], 'git_history_lookup_failed:' + workflow)
        self.assertFalse(report['sync_successor_approved'])


if __name__ == '__main__':
    unittest.main()

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

    def test_git_fatal_error_cannot_masquerade_as_an_absent_file(self):
        original_git = audit.git
        workflow = '.github/workflows/tablet-v1013-offdevice-compare.yml'
        for status, listing in ((128, b''), (0, b'100644 blob old\tworkflow\0')):
            def failed_tree(*args):
                if args == ('ls-tree', '-z', audit.V641_BASE, '--', workflow):
                    return type('Result', (), {'returncode': status, 'stdout': listing})()
                return original_git(*args)
            output = io.StringIO()
            with self.subTest(status=status, listing=listing), patch.object(audit, 'git', side_effect=failed_tree), contextlib.redirect_stdout(output):
                rc = audit.main()
            report = json.loads(output.getvalue())
            self.assertEqual(rc, 2)
            self.assertFalse(report['audit_complete'])
            self.assertEqual(report['hold_reason'], 'git_history_lookup_failed:' + workflow)
            self.assertFalse(report['sync_successor_approved'])

    def test_successor_scope_does_not_hide_unrelated_paths(self):
        from sync_v376_successor_test_support import preserve_reviewed_v1013_workflow_scope
        paths = ['unreviewed-extra.py', '.github/workflows/tablet-v1013-offdevice-compare.yml']
        self.assertEqual(
            preserve_reviewed_v1013_workflow_scope(paths, audit.V641_BASE, head=audit.V641_CANDIDATE),
            paths,
        )

    def test_successor_scope_rejects_tampered_workflow(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import sync_v376_successor_test_support as support
        workflow = support.V1013_WORKFLOW_PATH
        with TemporaryDirectory() as folder:
            root = Path(folder)
            target = root / workflow
            target.parent.mkdir(parents=True)
            target.write_bytes(b'altered-workflow')
            with patch.object(support, 'ROOT', root):
                self.assertEqual(
                    support.preserve_reviewed_v1013_workflow_scope([workflow], audit.V641_BASE),
                    [workflow],
                )


    def test_reviewed_workflow_absent_in_real_history_keeps_unrelated_paths(self):
        import sync_v376_successor_test_support as support
        workflow = support.V1013_WORKFLOW_PATH
        paths = ['unreviewed-extra.py', workflow]
        self.assertEqual(
            support.preserve_reviewed_v1013_workflow_scope(paths, audit.V641_BASE),
            ['unreviewed-extra.py'],
        )
        self.assertEqual(paths, ['unreviewed-extra.py', workflow])

    def test_successor_scope_rejects_failed_historical_tree_lookup(self):
        import subprocess
        import sync_v376_successor_test_support as support
        original = support._git_validation_run
        workflow = support.V1013_WORKFLOW_PATH
        for status in (1, 128):
            def failed_lookup(command, *args, **kwargs):
                if command[1:2] == ['ls-tree']:
                    return subprocess.CompletedProcess(command, status, b'', b'lookup failed')
                return original(command, *args, **kwargs)
            with self.subTest(status=status), patch.object(support, '_git_validation_run', side_effect=failed_lookup):
                self.assertEqual(
                    support.preserve_reviewed_v1013_workflow_scope([workflow], audit.V641_BASE),
                    [workflow],
                )

    def test_successor_scope_rejects_workflow_already_present_in_old_tree(self):
        import subprocess
        import sync_v376_successor_test_support as support
        original = support._git_validation_run
        workflow = support.V1013_WORKFLOW_PATH
        def present_in_history(command, *args, **kwargs):
            if command[1:2] == ['ls-tree']:
                return subprocess.CompletedProcess(command, 0, b'100644 blob old\t' + workflow.encode() + b'\0', b'')
            return original(command, *args, **kwargs)
        with patch.object(support, '_git_validation_run', side_effect=present_in_history):
            self.assertEqual(
                support.preserve_reviewed_v1013_workflow_scope([workflow], audit.V641_BASE),
                [workflow],
            )

    def test_successor_scope_rejects_unavailable_source_commit(self):
        import sync_v376_successor_test_support as support
        workflow = support.V1013_WORKFLOW_PATH
        self.assertEqual(
            support.preserve_reviewed_v1013_workflow_scope([workflow], '0' * 40),
            [workflow],
        )

    def test_successor_scope_rejects_changed_committed_workflow(self):
        import subprocess
        import sync_v376_successor_test_support as support
        original = support._git_validation_run
        workflow = support.V1013_WORKFLOW_PATH
        def changed_head(command, *args, **kwargs):
            if command == ['git', 'show', 'HEAD:' + workflow]:
                return subprocess.CompletedProcess(command, 0, b'unreviewed committed workflow', b'')
            return original(command, *args, **kwargs)
        with patch.object(support, '_git_validation_run', side_effect=changed_head):
            self.assertEqual(
                support.preserve_reviewed_v1013_workflow_scope([workflow], audit.V641_BASE),
                [workflow],
            )


if __name__ == '__main__':
    unittest.main()

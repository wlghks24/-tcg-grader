"""Reject altered BGS source, forged receipts and divergent review history."""
import copy
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import sync_v376_successor_test_support as sync


class BgsSourceSuccessorV867Tests(unittest.TestCase):
    def test_exact_candidate_and_legacy_cgc_delegation(self):
        sync.assert_v867_bgs_successor(self)
        name = sync.V563_CGC_PATH
        self.assertEqual([], sync.preserve_reviewed_v563_cgc_scope([name], sync.V563_CGC_BASE))
        self.assertEqual([name], sync.preserve_reviewed_v563_cgc_scope(
            [name], sync.V563_CGC_BASE, head=sync.V563_CGC_BASE))

    def test_each_live_pin_rechecked_after_history_cache_warmup(self):
        sync.assert_v867_bgs_successor(self)
        original = Path.read_bytes
        for name in sync.V867_BGS_PROOF['reviewed_sha256']:
            with self.subTest(path=name), patch.object(
                Path, 'read_bytes', lambda p: original(p) + b' unreviewed'
                if p == sync.ROOT / name else original(p)
            ):
                with self.assertRaises(AssertionError):
                    sync.assert_v867_bgs_successor(self)
                self.assertEqual([sync.V563_CGC_PATH], sync.preserve_reviewed_v563_cgc_scope(
                    [sync.V563_CGC_PATH], sync.V563_CGC_BASE))

    def test_forged_deployment_flags_fail_closed(self):
        original = sync._read
        for flag in ('physical_tablet_runtime_verified', 'deployment_allowed'):
            def forged(path):
                value = original(path)
                if str(path).endswith('bgs_source_successor_v867.json'):
                    value = copy.deepcopy(value)
                    value[flag] = True
                return value
            with self.subTest(flag=flag), patch.object(sync, '_read', side_effect=forged):
                with self.assertRaises(AssertionError):
                    sync.assert_v867_bgs_successor(self)

    def test_divergent_head_cannot_delegate_source(self):
        original = subprocess.run
        candidate = sync.V867_BGS_PROOF['candidate_commit']
        def divergent(args, *a, **kw):
            if args == ['git', 'merge-base', '--is-ancestor', candidate, 'HEAD']:
                return subprocess.CompletedProcess(args, 1)
            return original(args, *a, **kw)
        with patch.object(subprocess, 'run', side_effect=divergent):
            with self.assertRaises(AssertionError):
                sync.assert_v867_bgs_successor(self)
            self.assertEqual([sync.V563_CGC_PATH], sync.preserve_reviewed_v563_cgc_scope(
                [sync.V563_CGC_PATH], sync.V563_CGC_BASE))

    def test_symlinked_source_or_receipt_is_rejected(self):
        original = Path.is_symlink
        names = [sync.V563_CGC_PATH, '.github/tablet-autonomy/bgs_source_successor_v867.json']
        for name in names:
            with self.subTest(path=name), patch.object(
                Path, 'is_symlink', lambda p: p == sync.ROOT / name or original(p)
            ):
                with self.assertRaises(AssertionError):
                    sync.assert_v867_bgs_successor(self)

    def test_preexisting_changes_are_never_removed(self):
        source = sync.V563_CGC_CANDIDATE
        name = sync.V563_CGC_PATH
        self.assertEqual([name, 'unknown.py'], sync.preserve_reviewed_v563_cgc_scope(
            [name, 'unknown.py'], source))

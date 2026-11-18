"""Exact source coverage must not hide unknown paths or warmed-up tampering."""
from pathlib import Path
import unittest
from unittest.mock import patch
from execution.workspace_sync_scope_v1018 import reviewed_workspace_scope_v1018
ROOT=Path(__file__).resolve().parents[2]
class WorkspaceSyncScopeTests(unittest.TestCase):
    def test_known_paths_are_verified_and_unknown_paths_remain(self):
        paths=['index.html','verify_browser_runtime.js','unknown.py']
        covered=reviewed_workspace_scope_v1018(paths)
        self.assertEqual({'index.html','verify_browser_runtime.js'},covered)
        self.assertEqual({'unknown.py'},set(paths)-covered)
    def test_empty_or_unknown_only_never_claims_coverage(self):
        self.assertEqual(set(),reviewed_workspace_scope_v1018([]))
        self.assertEqual(set(),reviewed_workspace_scope_v1018(['main','other.js']))
    def test_live_tamper_rejected_after_a_successful_check(self):
        reviewed_workspace_scope_v1018(['index.html'])
        original=Path.read_bytes
        for name in ('index.html','verify_browser_runtime.js'):
            def changed(path,name=name):
                raw=original(path)
                return raw+b'UNREVIEWED' if path==ROOT/name else raw
            with self.subTest(name=name),patch.object(Path,'read_bytes',changed):
                with self.assertRaises(AssertionError):
                    reviewed_workspace_scope_v1018(['index.html'])

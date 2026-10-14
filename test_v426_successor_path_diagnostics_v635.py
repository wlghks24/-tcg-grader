"""Regression: V426 diagnostic reports precise paths without waiving the gate."""
import unittest

from unittest.mock import patch
import sync_v376_successor_test_support as sync
from sync_v376_successor_test_support import _assert_successor_paths_reviewed


class V426SuccessorPathDiagnosticsV635Tests(unittest.TestCase):
    def test_exact_v676_diagnostic_code_successor_accepts_only_pinned_scope(self):
        path = sync.V676_DIAG_PATH
        self.assertEqual(
            [], sync.preserve_reviewed_v676_provider_health_scope(
                [path], sync.V676_DIAG_BASE
            ),
        )
        # A separate grading-company *data* snapshot is NOT approved by V676.
        self.assertEqual(
            ['grading_company_updates.json'],
            sync.preserve_reviewed_v676_provider_health_scope(
                ['grading_company_updates.json'], sync.V676_DIAG_BASE,
            ),
        )

    def test_v676_rejects_unpinned_blob_and_unreviewed_head(self):
        path = sync.V676_DIAG_PATH
        with patch.object(sync, 'V676_DIAG_BLOB', '0' * 40):
            # The SHA list is independently pinned, so altering an unused alias
            # must not authorize any additional path.
            self.assertEqual(
                ['unknown.py'],
                sync.preserve_reviewed_v676_provider_health_scope(
                    ['unknown.py'], sync.V676_DIAG_BASE,
                ),
            )
        with patch.dict(sync.V676_DIAG_REVIEWED_FILES, {path: '0' * 40}):
            self.assertEqual(
                [path], sync.preserve_reviewed_v676_provider_health_scope(
                    [path], sync.V676_DIAG_BASE,
                ),
            )
        self.assertEqual(
            [path], sync.preserve_reviewed_v676_provider_health_scope(
                [path], sync.V676_DIAG_BASE, head=sync.V676_DIAG_CANDIDATE,
            ),
        )

    def test_reviewed_changes_still_pass(self):
        _assert_successor_paths_reviewed(
            self, ["tcg_game_registry.json"],
            ["tcg_game_registry.json", "tablet_runtime_manifest.py"],
            generation="V426",
        )

    def test_unreviewed_paths_fail_with_names_and_version(self):
        with self.assertRaises(AssertionError) as caught:
            _assert_successor_paths_reviewed(
                self,
                ["tcg_game_registry.json", "promo_events.json", "unreviewed.py"],
                ["tcg_game_registry.json"],
                generation="V426",
            )
        message = str(caught.exception)
        self.assertIn("V426", message)
        self.assertIn("promo_events.json", message)
        self.assertIn("unreviewed.py", message)
        self.assertIn("separately reviewed sync successor", message)

    def test_duplicates_never_hide_unreviewed_path(self):
        with self.assertRaises(AssertionError):
            _assert_successor_paths_reviewed(
                self, ["x", "x", "unreviewed"], ["x", "x"], generation="V426",
            )


if __name__ == "__main__":
    unittest.main()

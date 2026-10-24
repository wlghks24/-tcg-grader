"""Regression: V426 diagnostic reports precise paths without waiving the gate."""
import unittest

from sync_v376_successor_test_support import _assert_successor_paths_reviewed


class V426SuccessorPathDiagnosticsV635Tests(unittest.TestCase):
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

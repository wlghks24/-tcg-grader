"""V369 immutable diff memoization must never cache moving HEAD."""
import unittest
from unittest.mock import patch

import test_tablet_gpt_tcg_grader_sync_v369 as legacy


class V369DiffCacheTests(unittest.TestCase):
    def setUp(self):
        legacy._immutable_diff_paths.cache_clear()

    def tearDown(self):
        legacy._immutable_diff_paths.cache_clear()

    def test_immutable_pair_cached_and_head_uncached(self):
        source, candidate = "a" * 40, "b" * 40
        contract = {"freshness_watch": {
            "exact_paths": ["main", "index.html"],
            "path_prefixes": [],
            "exclude_paths": [],
        }}
        calls = []

        def read_diff(command, *, text):
            self.assertTrue(text)
            calls.append(tuple(command))
            if command[-1] == source + "..HEAD":
                count = sum(item[-1].endswith("..HEAD") for item in calls)
                return "main\n" if count == 1 else "index.html\n"
            return "main\n"

        with patch.object(legacy.subprocess, "check_output", side_effect=read_diff):
            with patch.object(legacy, "preserve_reviewed_v525_grade_scope",
                              side_effect=lambda visible, source, head: visible):
                self.assertEqual(["main"], legacy.watched_paths(contract, source, candidate))
                self.assertEqual(["main"], legacy.watched_paths(contract, source, candidate))
                self.assertEqual(["main"], legacy.watched_paths(contract, source))
                self.assertEqual(["index.html"], legacy.watched_paths(contract, source))

        self.assertEqual(3, len(calls))
        self.assertEqual(1, sum(item[-1] == source + ".." + candidate for item in calls))
        self.assertEqual(2, sum(item[-1] == source + "..HEAD" for item in calls))


if __name__ == "__main__":
    unittest.main()

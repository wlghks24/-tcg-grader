"""Run the recording-review DOM regressions from the existing root CI suite.

These deterministic fixtures are not browser rendering or Lenovo verification.
"""
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]


class VideoReviewDOMRepairsTests(unittest.TestCase):
    def test_cost_currency_and_incomplete_estimate_boundaries(self):
        self._node("execution/tests/test_grading_total_cost_20261122.js", "130 deterministic scenarios")

    def test_menu_resize_navigation_and_focus_boundaries(self):
        self._node("execution/tests/test_tablet_menu_shell_v903.js", "54 tests passed")

    def _node(self, relative, expected_count):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node is required; DOM checks cannot silently skip")
        result = subprocess.run(
            [node, relative], cwd=ROOT, text=True, capture_output=True,
            timeout=30, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS", result.stdout)
        # Fixture summaries prove real cases ran instead of a zero-test import.
        self.assertIn(expected_count, result.stdout)


if __name__ == "__main__":
    unittest.main()

"""Offline regression for TCG five-tool read-only adapter."""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from execution.tcg_five_tool_audit import ReviewBlocked, UPSTREAM, review


class TcgFiveToolAuditTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        for name, content in (
            ("core.py", "def compute(): pass\n"),
            ("one.py", "import core\n"),
            ("two.py", "import one\n"),
            ("tests/test_core.py", "import core\n"),
            ("unrelated.py", "import json\n"),
        ):
            self.add(name, content)

    def add(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", "--", name], cwd=self.root, check=True)

    def test_reverse_import_hops_and_candidate_tests(self):
        result = review(self.root, ["core.py"], depth=2)
        self.assertEqual([x["path"] for x in result["affected"]],
                         ["one.py", "tests/test_core.py", "two.py"])
        self.assertEqual(result["suggested_tests"], ["tests/test_core.py"])
        self.assertEqual(result["review_state"], "CANDIDATE_ONLY")
        self.assertFalse(result["physical_device_verified"])

    def test_absolute_from_package_module_is_in_impact_set(self):
        self.add("pkg/__init__.py", "")
        self.add("pkg/util.py", "VALUE = 1\n")
        self.add("consumer.py", "from pkg import util\n")
        result = review(self.root, ["pkg/util.py"], depth=1)
        self.assertIn("consumer.py", [row["path"] for row in result["affected"]])
        self.assertEqual(result["review_state"], "CANDIDATE_ONLY")

    def test_depth_zero_is_empty(self):
        result = review(self.root, ["core.py"], depth=0)
        self.assertEqual(result["affected"], [])
        self.assertTrue(result["depth_limited"])
        self.assertEqual(result["review_state"], "HOLD_INCOMPLETE_MAP")

    def test_depth_boundary_with_unseen_dependents_holds(self):
        self.add("three.py", "import two\n")
        result = review(self.root, ["core.py"], depth=2)
        self.assertEqual(result["review_state"], "HOLD_INCOMPLETE_MAP")
        self.assertTrue(result["depth_limited"])
        self.assertNotIn("three.py", [r["path"] for r in result["affected"]])

    def test_truncated_test_recommendations_hold(self):
        for i in range(15):
            self.add(f"tests/test_extra_{i:02d}.py", "import core\n")
        result = review(self.root, ["core.py"], depth=2, limit=40)
        self.assertEqual(result["suggested_tests_total"], 16)
        self.assertEqual(len(result["suggested_tests"]), 12)
        self.assertTrue(result["suggested_tests_truncated"])
        self.assertEqual(result["review_state"], "HOLD_INCOMPLETE_MAP")

    def test_bounded_truncation_blocks_approval(self):
        result = review(self.root, ["core.py"], limit=1)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["affected_total"], 3)
        self.assertEqual(result["review_state"], "HOLD_INCOMPLETE_MAP")

    def test_reject_invalid_paths(self):
        for name in ("../core.py", "/tmp/core.py", "core.py/../x.py",
                     "core.py\\x.py", ".env", "", "untracked.py"):
            with self.subTest(name=name):
                with self.assertRaises(ReviewBlocked):
                    review(self.root, [name])

    def test_reject_duplicate_or_excess_changes(self):
        with self.assertRaises(ReviewBlocked):
            review(self.root, ["core.py", "core.py"])
        with self.assertRaises(ReviewBlocked):
            review(self.root, ["core.py"] * 13)

    def test_symlinks_blocked(self):
        (self.root / "alias.py").symlink_to(self.root / "core.py")
        subprocess.run(["git", "add", "--", "alias.py"], cwd=self.root, check=True)
        with self.assertRaises(ReviewBlocked):
            review(self.root, ["alias.py"])

    def test_parse_issue_blocks_approval(self):
        self.add("broken.py", "import core\nbad ???\n")
        result = review(self.root, ["broken.py"])
        self.assertEqual(result["review_state"], "HOLD_INCOMPLETE_MAP")
        self.assertEqual(result["affected_parse_issues"], ["broken.py"])

    def test_is_deterministic_and_never_copies_code(self):
        first = review(self.root, ["core.py"])
        self.assertEqual(first, review(self.root, ["core.py"]))
        self.assertNotIn("def compute", str(first))

    def test_five_sources_and_never_real_install_claim(self):
        self.assertEqual(set(UPSTREAM), {"REA", "Agent Reach", "Graft",
                                        "Agency Agents", "Codebase Memory MCP"})
        report = review(self.root, ["core.py"])
        self.assertIn("NOT installed", " ".join(report["restrictions"]))

    def test_bad_limits_rejected(self):
        for kwargs in ({"depth": -1}, {"depth": 4}, {"limit": 0},
                       {"limit": 41}, {"depth": True}, {"limit": False}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ReviewBlocked):
                review(self.root, ["core.py"], **kwargs)


if __name__ == "__main__":
    unittest.main()

"""TCG read-only AST reverse engineering: real logic and failure contracts."""
from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from execution.tcg_reverse_engineering import ReverseBlocked, inspect


class ReverseEngineeringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)

    def add(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", "--", name], cwd=self.root, check=True)

    def test_calls_and_main_guard_are_static(self):
        self.add("core.py", "def run():\n    helper()\n    obj.call()\n\ndef helper(): pass\nif __name__ == '__main__':\n    run()\n")
        self.add("client.py", "import core\n")
        report = inspect(self.root, "core.py")
        self.assertEqual(report["possible_main_guard_lines"], [6])
        self.assertEqual(report["imported_by"], ["client.py"])
        self.assertEqual(report["defined_functions"][0]["observed_call_syntax"], ["*.call", "helper"])
        self.assertFalse(report["physical_tablet_verified"])
        self.assertEqual(report["review_state"], "CANDIDATE_ONLY")
        self.assertNotIn("obj.call()", str(report))

    def test_no_fake_entrypoint(self):
        self.add("utility.py", "def test():\n    print('hi')\n")
        self.assertEqual(inspect(self.root, "utility.py")["possible_main_guard_lines"], [])

    def test_nested_def_does_not_appear_as_parent_call(self):
        self.add("nested.py", "def outer():\n    def inner():\n        broken()\n    ok()\n")
        self.assertEqual(inspect(self.root, "nested.py")["defined_functions"][0]["observed_call_syntax"], ["ok"])

    def test_bounded_calls_result_hold(self):
        self.add("large.py", "def many():\n" + "".join(f"    func{i}()\n" for i in range(45)))
        report = inspect(self.root, "large.py")
        self.assertEqual(report["review_state"], "HOLD_TRUNCATED")
        self.assertEqual(len(report["defined_functions"][0]["observed_call_syntax"]), 40)

    def test_untracked_refused(self):
        (self.root / "secret.py").write_text("token = 'no'")
        with self.assertRaises(ReverseBlocked):
            inspect(self.root, "secret.py")

    def test_symlink_refused(self):
        self.add("real.py", "def run(): pass\n")
        link = self.root / "alias.py"
        link.symlink_to(self.root / "real.py")
        subprocess.run(["git", "add", "--", "alias.py"], cwd=self.root, check=True)
        with self.assertRaises(ReverseBlocked):
            inspect(self.root, "alias.py")

    def test_traversal_refused(self):
        self.add("main.py", "def hi(): pass\n")
        for name in ("../main.py", "/tmp/main.py", "main.py/../x.py", ".env"):
            with self.subTest(name=name), self.assertRaises(ReverseBlocked):
                inspect(self.root, name)

    def test_syntax_error_refused(self):
        self.add("broken.py", "def broken(:\n")
        with self.assertRaises(ReverseBlocked):
            inspect(self.root, "broken.py")

    def test_repeatable(self):
        self.add("main.py", "def hello():\n    print('hi')\n")
        self.assertEqual(inspect(self.root, "main.py"), inspect(self.root, "main.py"))


if __name__ == "__main__":
    unittest.main()

"""Deterministic tests for the read-only tracked code map."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from execution.tablet_code_map_audit import build


class TabletCodeMapAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)

    def add(self, name, content):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        subprocess.run(["git", "add", "--", name], cwd=self.root, check=True)

    def test_absolute_and_relative_imports(self):
        self.add("pkg/__init__.py", "")
        self.add("pkg/util.py", "VALUE = 1\n")
        self.add("pkg/sub/__init__.py", "")
        self.add("pkg/sub/worker.py", "from .. import util\nfrom pkg import util\n")
        report = build(self.root)
        self.assertIn("pkg/util.py", report["local_import_edges"]["pkg/sub/worker.py"])
        self.assertFalse(report["parse_issues"])
        self.assertFalse(report["physical_device_verified"])

    def test_malformed_and_oversize_are_reported(self):
        self.add("bad.py", "def broken(:\n")
        self.add("huge.py", "x" * 1_000_001)
        report = build(self.root)
        self.assertEqual(
            {x["path"]: x["issue"] for x in report["parse_issues"]},
            {"bad.py": "SyntaxError", "huge.py": "unsafe_or_oversize"},
        )

    def test_ignored_and_untracked_files_not_scanned(self):
        self.add("main.py", "import json\n")
        (self.root / "untracked.py").write_text("invalid !!", encoding="utf-8")
        self.add(".tmp/secret.py", "invalid !!")
        report = build(self.root)
        self.assertEqual(report["python_count"], 1)
        self.assertEqual(report["tracked_count"], 1)
        self.assertEqual(report["parse_issues"], [])


if __name__ == "__main__":
    unittest.main()

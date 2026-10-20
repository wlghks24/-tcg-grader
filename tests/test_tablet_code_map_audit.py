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

    def test_absolute_from_import_resolves_submodule(self):
        self.add("pkg/__init__.py", "")
        self.add("pkg/util.py", "VALUE = 1\n")
        self.add("consumer.py", "from pkg import util\n")
        report = build(self.root)
        self.assertIn("pkg/util.py", report["local_import_edges"]["consumer.py"])

    def test_shell_and_web_asset_candidates(self):
        self.add("run.sh", 'bash "scripts/check.sh"\n')
        self.add("scripts/check.sh", "echo ok\n")
        self.add("index.html", '<script src="app.js"></script>\n')
        self.add("app.js", "console.log(1);\n")
        report = build(self.root)
        self.assertIn("scripts/check.sh", report["static_asset_candidates"]["run.sh"])
        self.assertIn("app.js", report["static_asset_candidates"]["index.html"])
        self.assertFalse(report["physical_device_verified"])
    def test_query_suffix_and_relative_web_references(self):
        self.add("index.html", '<link rel="stylesheet" href="./style.css?v=3">\n'
                               '<script src="app.js#stable"></script>\n')
        self.add("style.css", "body { color: red }\n")
        self.add("app.js", "console.log(1)\n")
        report = build(self.root)
        self.assertIn("style.css", report["static_asset_candidates"]["index.html"])
        self.assertIn("app.js", report["static_asset_candidates"]["index.html"])

    def test_duplicate_basename_uses_explicit_relative_path(self):
        self.add("page/index.html", '<script src="../assets/one/app.js"></script>\n')
        self.add("assets/one/app.js", "console.log('one')\n")
        self.add("assets/two/app.js", "console.log('two')\n")
        report = build(self.root)
        self.assertEqual(report["static_asset_candidates"]["page/index.html"], ["assets/one/app.js"])
        self.assertEqual(report["ambiguous_asset_references"], [])
        self.assertGreaterEqual(report["scan_ms"], 0)
        self.assertGreaterEqual(report["quoted_references_examined"], 1)
        self.assertGreaterEqual(report["asset_files_scanned"], 3)

    def test_ambiguous_unqualified_basename_is_not_invented_as_edge(self):
        self.add("index.html", '<script src="app.js"></script>\n')
        self.add("assets/one/app.js", "// first\n")
        self.add("assets/two/app.js", "// second\n")
        report = build(self.root)
        self.assertEqual(report["static_asset_candidates"]["index.html"], [])
        self.assertIn({"source": "index.html", "basename": "app.js"},
                      report["ambiguous_asset_references"])

    def test_remote_url_not_classified_as_local_asset(self):
        self.add("index.html", '<script src="https://example.test/app.js"></script>\n')
        self.add("app.js", "console.log(1)\n")
        report = build(self.root)
        self.assertEqual(report["static_asset_candidates"]["index.html"], [])

    def test_unquoted_names_not_mistaken_for_literal_edges(self):
        self.add("run.sh", 'echo "unrelated" # scripts/check.sh is a comment\n')
        self.add("scripts/check.sh", "echo ok\n")
        report = build(self.root)
        self.assertNotIn("scripts/check.sh", report["static_asset_candidates"]["run.sh"])

    def test_replaced_parent_symlink_cannot_be_scanned(self):
        import os
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks not supported")
        with tempfile.TemporaryDirectory() as external:
            self.add("nested/unsafe.py", "import os\n")
            (self.root / "nested" / "unsafe.py").unlink()
            (self.root / "nested").rmdir()
            try:
                os.symlink(external, self.root / "nested", target_is_directory=True)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"symlink unavailable: {error}")
            (Path(external) / "unsafe.py").write_text("import sys\n", encoding="utf-8")
            report = build(self.root)
            self.assertEqual(report["parse_issues"][0]["path"], "nested/unsafe.py")
            self.assertEqual(report["parse_issues"][0]["issue"], "unsafe_or_oversize")
            self.assertNotIn("nested/unsafe.py", report["local_import_edges"])

    def test_graphify_missing_and_present_remain_read_only(self):
        self.add("main.py", "VALUE = 1\n")
        missing = build(self.root)["graphify_artifacts"]
        self.assertEqual(missing, {"graph.json": "missing", "graph_audit.json": "missing"})
        graphdir = self.root / "graphify-out"
        graphdir.mkdir()
        (graphdir / "graph.json").write_text('{"nodes":[]}', encoding="utf-8")
        present = build(self.root)["graphify_artifacts"]
        self.assertEqual(present["graph.json"], "present_unverified")
        self.assertEqual(present["graph_audit.json"], "missing")

    def test_graphify_symlink_outside_repository_is_not_trusted(self):
        import os
        self.add("main.py", "VALUE = 1\n")
        with tempfile.TemporaryDirectory() as external:
            (Path(external) / "graph.json").write_text('{"nodes":[]}', encoding="utf-8")
            try:
                os.symlink(external, self.root / "graphify-out", target_is_directory=True)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"symlink unavailable: {error}")
            report = build(self.root)
            self.assertEqual(report["graphify_artifacts"]["graph.json"], "unsafe_external_path")

    def test_short_asset_names_are_covered(self):
        self.add("index.html", '<script src="a.js"></script>\n')
        self.add("a.js", "console.log(1)\n")
        report = build(self.root)
        self.assertIn("a.js", report["static_asset_candidates"]["index.html"])

    def test_dirty_tracked_code_is_reported_without_modification(self):
        self.add("main.py", "BASELINE = 1\n")
        before = build(self.root)
        self.assertGreaterEqual(before["staged_tracked_changes"], 1)
        self.assertEqual(before["unstaged_tracked_changes"], 0)
        file = self.root / "main.py"
        file.write_text("BASELINE = 2\n", encoding="utf-8")
        after = build(self.root)
        self.assertGreaterEqual(after["staged_tracked_changes"], 1)
        self.assertGreaterEqual(after["unstaged_tracked_changes"], 1)
        self.assertEqual(file.read_text(encoding="utf-8"), "BASELINE = 2\n")

    def test_feature_router_does_not_write_pycache(self):
        import json
        import sys
        scanner = Path(__file__).resolve().parents[1] / "execution" / "tablet_code_map_audit.py"
        self.add("execution/tablet_code_map_audit.py",
                 scanner.read_text(encoding="utf-8"))
        self.add("code_map_intelligence.py",
                 "def resolve_feature_query(query):\n"
                 "    return {'query': query, 'read_only': True}\n")
        result = subprocess.run(
            [sys.executable, "execution/tablet_code_map_audit.py", "--feature", "tablet"],
            cwd=self.root, capture_output=True, text=True, check=True,
        )
        report = json.loads(result.stdout)
        self.assertEqual(report["existing_code_map_integration"],
                         "read_only_feature_route")
        self.assertEqual(report["existing_code_map_route"]["query"], "tablet")
        self.assertFalse((self.root / "__pycache__").exists())

    def test_untracked_source_is_inventoried_not_executed(self):
        self.add("tracked.py", "VALUE = 1\n")
        local = self.root / "local_tool.py"
        local.write_text("raise RuntimeError('do not execute me')\n", encoding="utf-8")
        report = build(self.root)
        self.assertEqual(report["untracked_inventory_status"], "names_only")
        self.assertEqual(report["untracked_entry_count"], 1)
        self.assertIn("local_tool.py", report["untracked_code_sample"])
        self.assertNotIn("local_tool.py", report["local_import_edges"])
        self.assertEqual(report["python_count"], 1)
        self.assertEqual(local.read_text(encoding="utf-8"),
                         "raise RuntimeError('do not execute me')\n")

    def test_untracked_backup_directory_is_only_one_inventory_entry(self):
        self.add("main.py", "VALUE = 1\n")
        backup = self.root / "backup_large"
        backup.mkdir()
        for index in range(15):
            (backup / f"file_{index}.py").write_text("UNTRUSTED = True\n", encoding="utf-8")
        report = build(self.root)
        self.assertEqual(report["untracked_entry_count"], 1)
        self.assertEqual(report["untracked_code_sample"], [])
        self.assertEqual(report["python_count"], 1)
        self.assertTrue((backup / "file_1.py").exists())

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

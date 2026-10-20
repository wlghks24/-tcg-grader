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

    def test_bounded_change_impact_finds_two_hop_python_test(self):
        from execution.tablet_code_map_audit import plan_change_impact
        self.add("lib.py", "VALUE = 1\n")
        self.add("consumer.py", "import lib\n")
        self.add("tests/test_consumer.py", "import consumer\n")
        report = build(self.root)
        plan = plan_change_impact(report, ["lib.py"])
        self.assertIn({"path": "consumer.py", "distance": 1},
                      plan["impact_candidates"])
        self.assertEqual(plan["test_candidates"], ["tests/test_consumer.py"])
        self.assertEqual(plan["initial_validation_scope"],
                         "targeted_plus_repository_verify")
        self.assertTrue(plan["full_regression_required_before_release"])
        self.assertEqual((self.root / "lib.py").read_text(), "VALUE = 1\n")

    def test_impact_unknown_or_critical_files_require_full_validation(self):
        from execution.tablet_code_map_audit import plan_change_impact
        self.add("safe_runtime.py", "VALUE = 1\n")
        report = build(self.root)
        for changed in ("untracked_local.py", ".github/workflows/ci.yml",
                        "safe_runtime.py", "../outside.py", "/etc/passwd"):
            plan = plan_change_impact(report, [changed])
            self.assertEqual(plan["initial_validation_scope"], "full_chain")
        self.assertEqual(
            plan_change_impact(report, ["untracked_local.py"])["unmapped_files"],
            ["untracked_local.py"],
        )

    def test_impact_static_web_references_are_candidates_not_verified(self):
        from execution.tablet_code_map_audit import plan_change_impact
        self.add("index.html", '<script src="app.js"></script>\n')
        self.add("app.js", "console.log(1)\n")
        report = build(self.root)
        plan = plan_change_impact(report, ["app.js"])
        self.assertEqual(plan["impact_candidates"],
                         [{"path": "index.html", "distance": 1}])
        self.assertEqual(plan["test_candidates"], [])
        self.assertEqual(plan["initial_validation_scope"], "repository_verify")
        self.assertIn("Static candidates only", plan["limitations"])

    def test_impact_caps_output_and_escalates_instead_of_skipping_tests(self):
        from execution.tablet_code_map_audit import plan_change_impact
        self.add("shared.py", "VALUE = 1\n")
        for index in range(6):
            self.add(f"test_user_{index}.py", "import shared\n")
        report = build(self.root)
        plan = plan_change_impact(report, ["shared.py"], max_tests=2)
        self.assertEqual(len(plan["test_candidates"]), 2)
        self.assertTrue(plan["bounded_impact_truncated"])
        self.assertEqual(plan["initial_validation_scope"], "full_chain")
        self.assertTrue(plan["full_regression_required_before_release"])

    def test_maintenance_queue_prioritizes_dirty_tree_and_parse_issues(self):
        from execution.tablet_code_map_audit import summarize_maintenance
        self.add("main.py", "VALUE = 1\n")
        report = build(self.root)
        report["parse_issues"] = [{"path": "bad.py", "issue": "SyntaxError"}]
        report["unresolved_asset_reference_count"] = 3
        report["incoming_reference_counts"] = {"a.py": 2, "b.py": 8}
        plan = summarize_maintenance(report)
        self.assertEqual([row["priority"] for row in plan["issues"][:2]],
                         ["P0", "P1"])
        self.assertEqual(plan["issues"][0]["category"], "local_worktree_protection")
        self.assertEqual(plan["import_hubs_for_review"][0]["path"], "b.py")
        self.assertIsNone(plan["quality_score"])
        self.assertFalse(plan["auto_source_change_authorized"])

    def test_clean_repository_report_has_no_unjustified_device_pass(self):
        self.add("main.py", "VALUE = 1\n")
        subprocess.run(["git", "-c", "user.email=test@example.invalid",
                        "-c", "user.name=test", "commit", "-qm", "baseline"],
                       cwd=self.root, check=True)
        report = build(self.root)
        q = report["maintenance_queue"]
        self.assertFalse(any(x["priority"] == "P0" for x in q["issues"]))
        self.assertFalse(q["physical_device_verified"])
        self.assertTrue(any(x["category"] == "graphify_evidence_incomplete"
                            for x in q["issues"]))

    def test_cli_changed_file_returns_read_only_impact_plan(self):
        import json
        import sys
        self.add("lib.py", "VALUE = 1\n")
        self.add("consumer.py", "import lib\n")
        scanner = Path(__file__).resolve().parents[1] / "execution" / "tablet_code_map_audit.py"
        proc = subprocess.run(
            [sys.executable, str(scanner), "--root", str(self.root),
             "--changed-file", "lib.py"],
            capture_output=True, text=True, check=True,
        )
        result = json.loads(proc.stdout)
        self.assertEqual(result["change_impact_plan"]["changed_files"], ["lib.py"])
        self.assertEqual(result["change_impact_plan"]["impact_candidates"],
                         [{"path": "consumer.py", "distance": 1}])
        self.assertFalse(result["physical_device_verified"])

    def test_component_inventory_separates_tracked_and_parseable_python(self):
        self.add("pkg/__init__.py", "")
        self.add("pkg/good.py", "VALUE = 1\n")
        self.add("pkg/bad.py", "def broken(:\n")
        self.add("tests/test_good.py", "import pkg.good\n")
        self.add("tests/helper.py", "import pkg.good\n")
        report = build(self.root)
        self.assertEqual(report["python_tracked_count"], 5)
        self.assertEqual(report["python_parsed_count"], 4)
        self.assertEqual(report["python_unscanned_count"], 1)
        self.assertEqual(report["python_count"], 4)  # backwards-compatible alias
        self.assertTrue(report["inventory_coverage_not_runtime_coverage"])
        by_area = {row["component"]: row for row in report["component_overview"]}
        self.assertEqual(by_area["pkg"]["tracked"], 3)
        self.assertEqual(by_area["pkg"]["python_parsed"], 2)
        self.assertEqual(by_area["tests"]["test_files"], 1)

    def test_impact_ignores_helper_module_as_test_but_keeps_dependency(self):
        from execution.tablet_code_map_audit import plan_change_impact
        self.add("lib.py", "VALUE = 1\n")
        self.add("tests/helper.py", "import lib\n")
        self.add("tests/test_lib.py", "import lib\n")
        report = build(self.root)
        plan = plan_change_impact(report, ["lib.py"])
        self.assertEqual(plan["test_candidates"], ["tests/test_lib.py"])
        self.assertIn({"path": "tests/helper.py", "distance": 1},
                      plan["impact_candidates"])
        self.assertTrue(plan["full_regression_required_before_release"])

    def test_inventory_reports_unreadable_assets_separately(self):
        self.add("index.html", '<script src="script.js"></script>\n')
        self.add("script.js", "console.log(1)\n")
        (self.root / "script.js").write_text("x" * 1_000_001, encoding="utf-8")
        report = build(self.root)
        self.assertEqual(report["asset_tracked_count"], 2)
        self.assertEqual(report["asset_files_scanned"], 1)
        self.assertEqual(report["asset_unscanned_count"], 1)
        self.assertTrue(any(row["path"] == "script.js" for row in report["parse_issues"]))

    def test_auto_change_inventory_combines_staged_and_unstaged(self):
        from execution.tablet_code_map_audit import collect_tracked_changes
        self.add("lib.py", "VALUE = 1\n")
        self.add("consumer.py", "import lib\n")
        subprocess.run(["git", "-c", "user.email=test@example.invalid",
                        "-c", "user.name=test", "commit", "-qm", "baseline"],
                       cwd=self.root, check=True)
        self.assertEqual(collect_tracked_changes(self.root)["status"], "clean")
        (self.root / "lib.py").write_text("VALUE = 2\n", encoding="utf-8")
        subprocess.run(["git", "add", "lib.py"], cwd=self.root, check=True)
        (self.root / "consumer.py").write_text("import lib\nVALUE = 3\n", encoding="utf-8")
        got = collect_tracked_changes(self.root)
        self.assertEqual(got, {"status": "changes", "files": ["consumer.py", "lib.py"]})
        self.assertEqual((self.root / "lib.py").read_text(), "VALUE = 2\n")
        self.assertEqual((self.root / "consumer.py").read_text(), "import lib\nVALUE = 3\n")

    def test_auto_change_cli_requires_no_changed_file_arguments(self):
        import json
        import sys
        scanner = Path(__file__).resolve().parents[1] / "execution" / "tablet_code_map_audit.py"
        self.add("lib.py", "VALUE = 1\n")
        self.add("consumer.py", "import lib\n")
        subprocess.run(["git", "-c", "user.email=test@example.invalid",
                        "-c", "user.name=test", "commit", "-qm", "baseline"],
                       cwd=self.root, check=True)
        (self.root / "lib.py").write_text("VALUE = 2\n", encoding="utf-8")
        before = (self.root / "lib.py").read_bytes()
        proc = subprocess.run(
            [sys.executable, str(scanner), "--root", str(self.root), "--auto-changes"],
            capture_output=True, text=True, check=True,
        )
        report = json.loads(proc.stdout)
        self.assertEqual(report["auto_change_inventory_status"], "changes")
        self.assertEqual(report["auto_changed_tracked_count"], 1)
        impact = report["change_impact_plan"]
        self.assertEqual(impact["changed_files"], ["lib.py"])
        self.assertIn({"path": "consumer.py", "distance": 1},
                      impact["impact_candidates"])
        self.assertTrue(impact["full_regression_required_before_release"])
        self.assertEqual((self.root / "lib.py").read_bytes(), before)

    def test_many_mapped_changes_escalate_when_display_is_truncated(self):
        from execution.tablet_code_map_audit import plan_change_impact
        files = [f"area/file_{i}.py" for i in range(52)]
        synthetic = {"local_import_edges": {p: [] for p in files},
                     "static_asset_candidates": {}, "parse_issues": []}
        result = plan_change_impact(synthetic, files)
        self.assertEqual(len(result["changed_files"]), 48)
        self.assertTrue(result["bounded_impact_truncated"])
        self.assertEqual(result["initial_validation_scope"], "full_chain")
        self.assertIn("bounded_impact_truncated", result["reasons"])

    def test_unavailable_auto_changes_must_not_be_called_clean(self):
        from unittest import mock
        from execution.tablet_code_map_audit import collect_tracked_changes
        with mock.patch("execution.tablet_code_map_audit.subprocess.run",
                        side_effect=OSError("git unavailable")):
            self.assertEqual(
                collect_tracked_changes(self.root),
                {"status": "unavailable", "files": []},
            )

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

    def test_nested_html_does_not_guess_same_name_from_wrong_directory(self):
        self.add("nested/index.html", '<script src="app.js"></script>\n'
                                      '<link href="../assets/site.css" rel="stylesheet">\n')
        self.add("app.js", "console.log('root only')\n")
        self.add("assets/site.css", "body {}\n")
        report = build(self.root)
        self.assertEqual(report["static_asset_candidates"]["nested/index.html"],
                         ["assets/site.css"])
        self.assertIn(
            {"source": "nested/index.html", "reference": "app.js", "candidate_count": 1},
            report["unresolved_asset_references"],
        )
        self.assertGreaterEqual(report["unresolved_asset_reference_count"], 1)

    def test_explicit_root_asset_path_resolves_only_root_target(self):
        self.add("nested/index.html", '<script src="/assets/app.js"></script>\n')
        self.add("assets/app.js", "console.log(1)\n")
        self.add("other/app.js", "console.log(2)\n")
        report = build(self.root)
        self.assertEqual(report["static_asset_candidates"]["nested/index.html"],
                         ["assets/app.js"])

    def test_missing_script_and_style_references_are_candidates_not_edges(self):
        self.add("index.html", '<script src="missing.js"></script>\n'
                               '<link rel="stylesheet" href="missing.css">\n')
        report = build(self.root)
        self.assertEqual(report["static_asset_candidates"]["index.html"], [])
        self.assertEqual(report["unresolved_asset_reference_count"], 2)
        self.assertEqual(
            {row["reference"]: row["candidate_count"]
             for row in report["unresolved_asset_references"]},
            {"missing.js": 0, "missing.css": 0},
        )

    def test_nested_shell_script_resolves_root_relative_command_candidate(self):
        self.add("scripts/setup.sh", 'bash "helpers/run.sh"\n')
        self.add("helpers/run.sh", "echo ok\n")
        report = build(self.root)
        self.assertEqual(report["static_asset_candidates"]["scripts/setup.sh"],
                         ["helpers/run.sh"])
        self.assertEqual(report["unresolved_asset_reference_count"], 0)

    def test_nested_shell_ambiguous_cwd_and_script_paths_do_not_invent_edge(self):
        self.add("scripts/setup.sh", 'bash "helpers/run.sh"\n')
        self.add("helpers/run.sh", "echo from repo root\n")
        self.add("scripts/helpers/run.sh", "echo from script directory\n")
        report = build(self.root)
        self.assertEqual(report["static_asset_candidates"]["scripts/setup.sh"], [])
        self.assertEqual(report["unresolved_asset_reference_count"], 1)
        self.assertEqual(report["ambiguous_asset_reference_count"], 1)
        self.assertEqual(report["ambiguous_asset_references"],
                         [{"source": "scripts/setup.sh", "basename": "run.sh"}])

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

    def test_graphify_cli_probe_never_executes_binary(self):
        from unittest import mock
        self.add("main.py", "VALUE = 1\n")
        # A real runner binary is not required; capability detection cannot
        # execute the tool or create graph outputs.
        with mock.patch("execution.tablet_code_map_audit.shutil.which",
                        return_value="/tmp/fake-graphify"):
            report = build(self.root)
        self.assertEqual(report["graphify_cli_status"], "present_unverified")
        self.assertEqual(report["graphify_artifacts"],
                         {"graph.json": "missing", "graph_audit.json": "missing"})
        self.assertFalse((self.root / "graphify-out").exists())

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

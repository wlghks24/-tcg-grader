"""V661 tablet code atlas: pure read-only inventory and impact regressions."""
import tempfile
import unittest
from pathlib import Path
from execution.tablet_code_atlas_v661 import atlas, role, safe_name


class AtlasTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.sources = {
            "main": "python tablet_autonomous_evolution_v400.py --self-test\n",
            "TABLET_SCHEDULED_UPDATE.sh": "python tablet_autonomous_evolution_v400.py --execute-safe-learning\n",
            "tablet_autonomous_evolution_v399.py": "import safe_runtime\n",
            "tablet_autonomous_evolution_v400.py": "import tablet_autonomous_evolution_v399\n",
            "safe_runtime.py": "def save(): pass\n",
            "test_tablet_autonomous_evolution_v400.py": "import tablet_autonomous_evolution_v400\n",
            "TCG_CROSSCHECK/old_sync.json": "{}",
            "snapshot.json": "{}",
        }
        for p, s in self.sources.items():
            f = self.root / p
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(s, encoding="utf-8")

    def run_atlas(self, **kwargs):
        return atlas(self.root, sorted(self.sources),
                     active=("main", "tablet_autonomous_evolution_v400.py"), **kwargs)

    def test_full_index_no_deletion(self):
        r = self.run_atlas(detailed=True)
        self.assertTrue(r["ok"], r["errors"])
        self.assertEqual(len(self.sources), r["tracked_count"])
        self.assertEqual([399, 400], r["autonomy_versions"])
        self.assertIn("TCG_CROSSCHECK/old_sync.json",
                      r["tracked_paths_by_role"]["preserved_crosscheck_contract_or_snapshot"])
        self.assertFalse(r["auto_deletion"])

    def test_static_imports_and_shell_edges(self):
        r = self.run_atlas(detailed=True)
        self.assertIn("tablet_autonomous_evolution_v400.py", r["dependencies"]["main"])
        self.assertIn("tablet_autonomous_evolution_v399.py",
                      r["dependencies"]["tablet_autonomous_evolution_v400.py"])

    def test_change_impact_and_tests(self):
        r = self.run_atlas(changed=("tablet_autonomous_evolution_v400.py",))
        self.assertIn("test_tablet_autonomous_evolution_v400.py", r["existing_test_candidates"])
        self.assertEqual("FULL_CI_AND_SUCCESSOR_CONTRACT", r["recommended_review"])

    def test_old_controller_is_still_a_dependency(self):
        r = self.run_atlas(changed=("tablet_autonomous_evolution_v399.py",))
        self.assertIn("tablet_autonomous_evolution_v400.py", r["impacted_files"])

    def test_missing_active_fails_closed(self):
        r = atlas(self.root, sorted(self.sources), active=("missing.py",))
        self.assertFalse(r["ok"])
        self.assertEqual(["missing.py"], r["missing_active"])

    def test_syntax_error_fails_closed(self):
        (self.root / "tablet_autonomous_evolution_v400.py").write_text("def oops(:\n")
        self.assertFalse(self.run_atlas()["ok"])

    def test_symlink_fails_closed(self):
        p = self.root / "tablet_autonomous_evolution_v400.py"
        p.unlink()
        p.symlink_to(self.root / "safe_runtime.py")
        self.assertIn("UNSAFE_OR_MISSING_SOURCE:tablet_autonomous_evolution_v400.py",
                      self.run_atlas()["errors"])

    def test_bad_changed_path_rejected(self):
        with self.assertRaisesRegex(ValueError, "UNSAFE_CHANGED_PATH"):
            self.run_atlas(changed=("../private.py",))
        self.assertFalse(safe_name("/secret.py"))

    def test_untracked_change_is_warning(self):
        r = self.run_atlas(changed=("new_file.py",))
        self.assertTrue(r["ok"])
        self.assertTrue(any("UNTRACKED_CHANGED_PATHS" in x for x in r["warnings"]))

    def test_no_module_import_execution(self):
        (self.root / "tablet_autonomous_evolution_v399.py").write_text("raise RuntimeError('never import')\n")
        self.assertTrue(self.run_atlas()["ok"])

    def test_skill_mirror_equal_is_not_deletion(self):
        a, b = ".agents/skills/foo/SKILL.md", ".codex/skills/foo/SKILL.md"
        for name in (a, b):
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("unchanged")
        from execution.tablet_code_atlas_v661 import mirror_health
        r = mirror_health(self.root, sorted(self.sources) + [a, b])
        self.assertEqual("MIRRORS_MATCH", r["status"])
        self.assertEqual(1, r["matching"])
        self.assertFalse(r["deletion_authorized"])

    def test_skill_mirror_drift_only_requests_review(self):
        a, b = "AGENTS.md", "CLAUDE.md"
        (self.root / a).write_text("A")
        (self.root / b).write_text("B")
        from execution.tablet_code_atlas_v661 import mirror_health
        r = mirror_health(self.root, sorted(self.sources) + [a, b])
        self.assertEqual("MIRROR_DRIFT_REVIEW", r["status"])
        self.assertEqual(1, r["drift_count"])
        self.assertEqual("A", (self.root / a).read_text())

    def test_mirror_symlink_is_blocked(self):
        a, b = "AGENTS.md", "CLAUDE.md"
        (self.root / a).write_text("A")
        (self.root / b).symlink_to(self.root / a)
        from execution.tablet_code_atlas_v661 import mirror_health
        r = mirror_health(self.root, sorted(self.sources) + [a, b])
        self.assertEqual("MIRROR_READ_HOLD", r["status"])
        self.assertTrue(r["errors"])

    def test_repeatable_and_read_only(self):
        before = {p: (self.root / p).read_bytes() for p in self.sources}
        one = self.run_atlas()
        two = self.run_atlas()
        self.assertEqual(one, two)
        self.assertEqual(before, {p: (self.root / p).read_bytes() for p in self.sources})

    def test_no_false_ai_confidence_or_device_claim(self):
        r = self.run_atlas()
        self.assertFalse(r["physical_device_verified"])
        self.assertEqual(0, r["learning_records_created"])
        self.assertFalse(r["graphify_replaced"])


if __name__ == "__main__":
    unittest.main()

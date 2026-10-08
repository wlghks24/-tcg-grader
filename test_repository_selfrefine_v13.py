#!/usr/bin/env python3
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import fault_injection_healing as healing
import repository_integrity_guard as guard


ROOT = Path(__file__).resolve().parent


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


class RepositorySelfrefineV13Tests(unittest.TestCase):
    def test_cross_platform_text_suffixes_are_in_integrity_scope(self):
        for suffix in (".py", ".js", ".html", ".yml", ".yaml", ".sh", ".command", ".bat", ".cmd", ".ps1"):
            self.assertIn(suffix, guard.EXECUTABLE_TEXT_SUFFIXES)
            self.assertIn(suffix, guard.TEXT_SUFFIXES)
        for suffix in (".json", ".webmanifest"):
            self.assertIn(suffix, guard.JSON_TEXT_SUFFIXES)
            self.assertIn(suffix, guard.TEXT_SUFFIXES)

    def test_manifest_is_strict_json(self):
        text = (ROOT / "manifest.webmanifest").read_text(encoding="utf-8")
        parsed = json.loads(
            text,
            object_pairs_hook=guard.unique_object,
            parse_constant=guard.reject_constant,
        )
        self.assertIsInstance(parsed, dict)
        self.assertTrue(parsed.get("name") or parsed.get("short_name"))


    def test_integrity_manifest_rejects_new_unlisted_git_tracked_file(self):
        with tempfile.TemporaryDirectory(prefix="tcg-manifest-completeness-") as directory:
            root = Path(directory)
            _git(root, "init", "-q")
            (root / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
            _git(root, "add", "sample.py")
            manifest = root / "integrity_manifest.json"
            healing.build_integrity_manifest(root, manifest)
            self.assertEqual(guard.integrity_manifest_findings(root), [])
            (root / "late_added.py").write_text("VALUE = 2\n", encoding="utf-8")
            _git(root, "add", "late_added.py")
            self.assertIn(
                "integrity manifest missing tracked path: late_added.py",
                guard.integrity_manifest_findings(root),
            )

    def test_integrity_manifest_ignores_untracked_runtime_artifact(self):
        with tempfile.TemporaryDirectory(prefix="tcg-manifest-runtime-") as directory:
            root = Path(directory)
            _git(root, "init", "-q")
            (root / ".gitignore").write_text("RUNTIME_REPORT.json\n", encoding="utf-8")
            (root / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
            _git(root, "add", ".gitignore", "sample.py")
            manifest = root / "integrity_manifest.json"
            healing.build_integrity_manifest(root, manifest)
            (root / "RUNTIME_REPORT.json").write_text('{"status":"runtime"}\n', encoding="utf-8")
            self.assertEqual(guard.integrity_manifest_findings(root), [])

    def test_integrity_manifest_rejects_hash_drift(self):
        with tempfile.TemporaryDirectory(prefix="tcg-manifest-hash-") as directory:
            root = Path(directory)
            target = root / "sample.py"
            target.write_text("VALUE = 1\n", encoding="utf-8")
            manifest = root / "integrity_manifest.json"
            healing.build_integrity_manifest(root, manifest)
            target.write_text("VALUE = 9\n", encoding="utf-8")
            self.assertIn(
                "integrity manifest hash/schema mismatch: sample.py",
                guard.integrity_manifest_findings(root),
            )

    def test_current_runtime_cannot_import_one_shot_patchers(self):
        self.assertIsNotNone(
            guard.legacy_runtime_reference(
                "auto_update_all.py",
                "from apply_old_patch import apply\n",
            )
        )
        self.assertIsNotNone(
            guard.legacy_runtime_reference(
                "START_TCG_UPDATER_ANDROID.sh",
                "python3 apply_old_patch.py\n",
            )
        )

    def test_read_only_workflow_may_replay_patcher_for_deterministic_validation(self):
        safe = """name: validate
on:
  pull_request:
permissions:
  contents: read
jobs:
  check:
    steps:
      - run: python apply_catalog_image_patch.py
"""
        self.assertIsNone(
            guard.legacy_runtime_reference(".github/workflows/catalog-image-sync.yml", safe)
        )

    def test_hidden_write_workflow_cannot_execute_patcher(self):
        unsafe = """name: mutate
on:
  push:
    branches: [main]
permissions:
  contents: write
jobs:
  patch:
    steps:
      - run: python apply_hidden_patch.py
      - run: git push origin HEAD:main
"""
        self.assertIsNotNone(
            guard.legacy_runtime_reference(".github/workflows/hidden-sync.yml", unsafe)
        )

    def test_current_runtime_cannot_reference_archived_gemini_sources(self):
        self.assertIsNotNone(
            guard.legacy_runtime_reference(
                "tcg_updater.py",
                "ARCHIVE = 'gemini-code-1787475518290.py'\n",
            )
        )

    def test_archived_patch_and_regression_files_may_reference_their_own_history(self):
        self.assertIsNone(
            guard.legacy_runtime_reference(
                "apply_old_patch.py",
                "python3 apply_old_patch.py\n",
            )
        )
        self.assertIsNone(
            guard.legacy_runtime_reference(
                "test_repository_selfrefine_v13.py",
                "from apply_old_patch import apply\n",
            )
        )
        self.assertIsNone(
            guard.legacy_runtime_reference(
                ".github/workflows/apply-old.yml",
                "run: python apply_old_patch.py\n",
            )
        )

    def test_runtime_delivery_guard_does_not_pin_stale_asset_revision(self):
        source = (ROOT / "test_runtime_delivery_guards.py").read_text(encoding="utf-8")
        self.assertNotIn("auto_validation_flow.js?v=181", source)
        self.assertNotIn("graded_photo_dashboard.js?v=181", source)
        self.assertIn("cache-buster regressed", source)
        self.assertIn("network-first-runtime", source)

    def test_runtime_bundle_coverage_contract_tracks_shared_taxonomy(self):
        import runtime_bundle_guard_v143 as runtime_guard
        import update_promo_events as promo

        result = runtime_guard.audit()
        collector = promo.multi_route_event_discovery
        expected = len(collector.GAMES) * len(collector.REGIONS) * len(
            collector.COVERAGE_TOPICS
        )
        self.assertGreaterEqual(expected, 207)
        self.assertEqual(result["contracts"]["event_coverage_cells"], expected)

    def test_repository_guard_runs_before_merge_without_path_blindspots(self):
        workflow = (ROOT / ".github/workflows/repository-integrity-guard.yml").read_text(encoding="utf-8")
        self.assertIn("  pull_request:", workflow)
        self.assertIn("  push:\n    branches: [main]", workflow)
        self.assertNotIn("    paths:", workflow)
        self.assertIn("python repository_integrity_guard.py", workflow)
        self.assertIn("security_self_audit.py --no-memory --fail-on high", workflow)
        self.assertIn("'*.sh' '*.command'", workflow)
        self.assertIn("test_repository_selfrefine_v13.py", workflow)


if __name__ == "__main__":
    unittest.main()

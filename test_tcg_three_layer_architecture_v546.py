#!/usr/bin/env python3
"""V546: executable, dependency-free three-layer policy and credentials regressions."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from execution.architecture_audit import REPO_ROOT, audit


class ThreeLayerArchitectureV546(unittest.TestCase):
    def fixture(self, root: Path) -> None:
        guidance = (
            "# AGENTS.md\n"
            "tcg-skill-router fail-closed local-only\n"
            "## Three-layer project architecture\n"
            "directives/ and execution/\n"
        )
        for name in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
            (root / name).write_text(guidance, encoding="utf-8")
        (root / "directives").mkdir()
        (root / "directives" / "TCG_RELIABILITY_SOP.md").write_text(
            "## 1. Directive\n## 2. Orchestration\n## 3. Execution\n"
            "## 4. Verified self-annealing\n403 current-head physical\n",
            encoding="utf-8",
        )
        (root / "execution").mkdir()
        for name in ("main", "agent_skills_guard.py", "safe_runtime.py",
                     "main_selfrefine_gate.py", "tablet_runtime_manifest.py"):
            (root / name).write_text("safe", encoding="utf-8")
        (root / ".gitignore").write_text(
            ".tmp/\n.env\n.env.*\ncredentials*.json\ntoken.json\n", encoding="utf-8"
        )
        (root / ".graphifyignore").write_text(
            "AGENTS.md\nCLAUDE.md\nGEMINI.md\ndirectives/\n", encoding="utf-8"
        )

    def test_actual_repository_contract(self):
        report = audit(REPO_ROOT)
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual([], report["errors"])
        self.assertEqual(0, report["mutations"])
        self.assertEqual(0, report["network_calls"])
        self.assertFalse(report["physical_device_verified"])

    def test_valid_fixture(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.fixture(root)
            report = audit(root, tracked=["AGENTS.md", "main", "execution/architecture_audit.py"])
            self.assertTrue(report["ok"], report["errors"])
            self.assertEqual(3, report["checked_tracked_files"])

    def test_rejects_drifted_mirror_and_missing_sop(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.fixture(root)
            (root / "CLAUDE.md").write_text("unexpected", encoding="utf-8")
            (root / "directives" / "TCG_RELIABILITY_SOP.md").unlink()
            report = audit(root, tracked=[])
            self.assertFalse(report["ok"])
            self.assertIn("guidance_mirror_mismatch", report["errors"])
            self.assertIn("directive_missing_or_unsafe", report["errors"])

    def test_rejects_tracked_secrets_without_exposing_values(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.fixture(root)
            names = [".tmp/work.json", ".env", ".env.production", "token.json",
                     "credentials.json", "nested/oauth_token_backup.json"]
            report = audit(root, tracked=names)
            self.assertFalse(report["ok"])
            self.assertIn("tracked_secret_or_scratch_paths:6", report["errors"])
            self.assertNotIn("nested", str(report))
            self.assertNotIn("production", str(report))

    def test_allows_placeholder_env_example_and_regular_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.fixture(root)
            report = audit(root, tracked=[".env.example", "tests/metadata.json",
                                           "execution/architecture_audit.py"])
            self.assertTrue(report["ok"], report["errors"])

    def test_case_insensitive_human_directive_wording(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.fixture(root)
            path = root / "directives" / "TCG_RELIABILITY_SOP.md"
            path.write_text(path.read_text(encoding="utf-8").replace(
                "physical", "Physical"
            ), encoding="utf-8")
            report = audit(root, tracked=[])
            self.assertTrue(report["ok"], report["errors"])

    def test_rejects_missing_ignored_token(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.fixture(root)
            (root / ".gitignore").write_text(".tmp/\n.env\n.env.*\ncredentials*.json\n",
                                            encoding="utf-8")
            report = audit(root, tracked=[])
            self.assertFalse(report["ok"])
            self.assertIn("missing_policy_ignore:.gitignore:token.json", report["errors"])


if __name__ == "__main__":
    unittest.main()

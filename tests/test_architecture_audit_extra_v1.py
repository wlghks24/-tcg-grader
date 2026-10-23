"""Read-only extra regressions for TCG three-layer architecture audit.

Run: python -m unittest discover -s tests -p 'test_architecture_audit_extra_v1.py' -v
This file does not mutate any tracked source; fixtures use temporary directories.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from execution.architecture_audit import _secret_path, audit


def fixture(root: Path) -> None:
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
    for name in ("main", "agent_skills_guard.py", "safe_runtime.py",
                 "main_selfrefine_gate.py", "tablet_runtime_manifest.py"):
        (root / name).write_text("fixture", encoding="utf-8")
    (root / ".gitignore").write_text(
        ".tmp/\n.env\n.env.*\ncredentials*.json\ntoken.json\n", encoding="utf-8"
    )
    (root / ".graphifyignore").write_text(
        "AGENTS.md\nCLAUDE.md\nGEMINI.md\ndirectives/\n", encoding="utf-8"
    )


class ExtraArchitectureAuditTests(unittest.TestCase):
    def test_valid_fixture_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture(root)
            self.assertTrue(audit(root, tracked=["README.md"])["ok"])

    def test_tracked_credential_glob_variants_blocked(self):
        for path in ("credentials_backup.json", "config/CREDENTIALS-PROD.JSON"):
            with self.subTest(path=path):
                self.assertTrue(_secret_path(path), path)

    def test_audit_blocks_tracked_credential_glob(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture(root)
            report = audit(root, tracked=["config/credentials_backup.json"])
            self.assertFalse(report["ok"])
            self.assertIn("tracked_secret_or_scratch_paths:1", report["errors"])

    def test_uppercase_scratch_dir_blocked(self):
        self.assertTrue(_secret_path(".TMP/cache.json"))

    def test_safe_placeholders_not_blocked(self):
        for path in (".env.example", "docs/credentials.md", "safe/report.json"):
            with self.subTest(path=path):
                self.assertFalse(_secret_path(path), path)

    def test_symlinked_guidance_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture(root)
            (root / "CLAUDE.md").unlink()
            (root / "CLAUDE.md").symlink_to(root / "AGENTS.md")
            report = audit(root, tracked=[])
            self.assertFalse(report["ok"])
            self.assertIn("unsafe_or_missing_guidance:CLAUDE.md", report["errors"])

    def test_missing_graphify_ignore_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture(root)
            (root / ".graphifyignore").unlink()
            report = audit(root, tracked=[])
            self.assertIn("unsafe_or_missing_policy:.graphifyignore", report["errors"])

    def test_tracked_sensitive_name_redacted_from_report(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture(root)
            report = audit(root, tracked=["secret/credentials.json"])
            self.assertFalse(report["ok"])
            self.assertIn("tracked_secret_or_scratch_paths:1", report["errors"])
            self.assertNotIn("secret/", str(report))

    def test_report_never_claims_device_verified(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fixture(root)
            report = audit(root, tracked=[])
            self.assertEqual(0, report["network_calls"])
            self.assertEqual(0, report["mutations"])
            self.assertFalse(report["physical_device_verified"])


if __name__ == "__main__":
    unittest.main()

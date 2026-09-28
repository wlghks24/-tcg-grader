import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import static_integrity_manifest as static_integrity


class StaticIntegrityManifestV345Tests(unittest.TestCase):
    def _git(self, root: Path, *args: str) -> None:
        subprocess.run(["git", *args], cwd=root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_untracked_runtime_json_is_never_added_to_fixed_hash_manifest(self):
        with tempfile.TemporaryDirectory(prefix="tcg-static-integrity-") as directory:
            root = Path(directory)
            self._git(root, "init")
            tracked = root / "source.py"
            tracked.write_text("VALUE = 1\n", encoding="utf-8")
            (root / "runtime_report.json").write_text('{"runtime":true}\n', encoding="utf-8")
            self._git(root, "add", "source.py")
            payload = static_integrity.build_manifest(root)
            self.assertIn("source.py", payload["files"])
            self.assertNotIn("runtime_report.json", payload["files"])

    def test_manifest_check_fails_on_tracked_content_drift(self):
        with tempfile.TemporaryDirectory(prefix="tcg-static-integrity-drift-") as directory:
            root = Path(directory)
            self._git(root, "init")
            tracked = root / "source.py"
            tracked.write_text("VALUE = 1\n", encoding="utf-8")
            self._git(root, "add", "source.py")
            manifest = root / "integrity_manifest.json"
            static_integrity.build_manifest(root, manifest)
            tracked.write_text("VALUE = 2\n", encoding="utf-8")
            result = static_integrity.check_manifest(root, manifest)
            self.assertFalse(result["ok"])
            self.assertEqual(["source.py"], result["mismatched"])

    def test_refresh_restores_only_unstaged_tracked_drift_before_manifest(self):
        workflow = Path('.github/workflows/tcg-static-data-refresh.yml').read_text(encoding='utf-8')
        self.assertIn("git diff --name-only -z", workflow)
        self.assertIn("git restore --worktree --", workflow)
        self.assertIn("python static_integrity_manifest.py --write integrity_manifest.json", workflow)
        self.assertIn("python static_integrity_manifest.py --check integrity_manifest.json", workflow)
        self.assertNotIn("python fault_injection_healing.py --manifest", workflow)

    def test_manifest_sync_allows_owner_fix_and_ops_branches_only(self):
        workflow = Path('.github/workflows/repository-integrity-manifest-sync-v345.yml').read_text(encoding='utf-8')
        self.assertIn("- 'fix/**'", workflow)
        self.assertIn("- 'ops/**'", workflow)
        self.assertIn('test "${GITHUB_ACTOR}" = "${GITHUB_REPOSITORY_OWNER}"', workflow)
        self.assertIn('fix/*|ops/*', workflow)
        self.assertIn('git merge-base --is-ancestor origin/main HEAD', workflow)
        self.assertIn('test "$(git rev-parse --abbrev-ref HEAD)" != "main"', workflow)
        self.assertIn("test \"$(git diff --cached --name-only)\" = \"integrity_manifest.json\"", workflow)
        self.assertIn("Reconcile integrity manifest for owner repair branch", workflow)
        self.assertNotIn("HEAD:main", workflow)
        self.assertNotIn("branches-ignore:", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)

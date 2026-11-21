"""Real-Git and real-file regressions for Lenovo second backup inspection."""
from __future__ import annotations

import hashlib
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from execution import tablet_secondary_backup_audit as audit


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], text=True,
                          capture_output=True, check=True, timeout=30).stdout.strip()


class SecondaryBackupTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory(prefix="tcg-lenovo-second-copy-")
        self.addCleanup(d.cleanup)
        self.home = Path(d.name)
        self.repo = self.home / "repo"
        self.first = self.home / "on_tablet"
        self.second = self.home / "external_copy"
        self.extra = "local-extra-example"
        self.repo.mkdir()
        (self.first / self.extra).mkdir(parents=True)
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.name", "Test")
        git(self.repo, "config", "user.email", "test@example.invalid")
        git(self.repo, "remote", "add", "origin",
            "https://github.com/wlghks24/-tcg-grader.git")
        (self.repo / "learning.json").write_text('{"data":"baseline"}\n')
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "base")
        git(self.repo, "update-ref", "refs/remotes/origin/main",
            git(self.repo, "rev-parse", "HEAD"))
        (self.repo / "learning.json").write_text('{"data":"private local"}\n')
        shutil.copy2(self.repo / "learning.json", self.first / "learning.json")
        (self.first / "SHA256SUMS").write_text(
            sha(self.first / "learning.json") + "  learning.json\n")
        bundle = self.first / "operating-history.bundle"
        git(self.repo, "bundle", "create", str(bundle), "--all", "HEAD")
        (self.first / "operating-history.bundle.sha256").write_text(
            sha(bundle) + "  operating-history.bundle\n")
        private = self.first / self.extra / "files" / "PRIVATE" / "raw.jpg"
        private.parent.mkdir(parents=True)
        private.write_bytes(b"dummy local photo data")
        (self.first / self.extra / "MANIFEST.json").write_text(json.dumps({
            "schema": "tablet-local-extra-preserve-v1", "complete": True,
            "files": [{"path": "PRIVATE/raw.jpg", "bytes": private.stat().st_size,
                       "sha256": sha(private), "verified": True}],
        }))
        shutil.copytree(self.first, self.second)
        self.original_hashes = {
            p.relative_to(self.first): sha(p)
            for p in self.first.rglob("*") if p.is_file()
        }

    def examine(self, *, distinct=True):
        if distinct:
            with patch.object(audit, "_filesystem_id",
                              side_effect=lambda p: 9 if Path(p) == self.second else 7):
                return audit.inspect(self.repo, self.first, self.second, self.extra,
                                     expected_tracked=1, expected_extra=1)
        return audit.inspect(self.repo, self.first, self.second, self.extra,
                             expected_tracked=1, expected_extra=1)

    def test_copied_bundle_json_and_private_file_are_verified_but_install_is_hold(self):
        result = self.examine()
        self.assertEqual("SECONDARY_FILESYSTEM_COPY_VERIFIED_INSTALL_HOLD",
                         result["status"], result)
        self.assertTrue(result["backup_verified"])
        self.assertTrue(result["distinct_filesystem_copy_verified"])
        self.assertTrue(result["git_bundle_verified"])
        self.assertEqual(1, result["tracked_files_verified"])
        self.assertEqual(1, result["private_files_verified"])
        for key in ("physical_offdevice_custody_verified",
                    "quiesced_snapshot_verified", "restoration_test_verified",
                    "current_protected_main_ci_verified", "code_release_approved",
                    "physical_lenovo_runtime_verified", "install_allowed",
                    "writes_or_updates_performed"):
            self.assertIs(result[key], False)
        self.assertEqual(self.original_hashes, {
            p.relative_to(self.first): sha(p)
            for p in self.first.rglob("*") if p.is_file()
        })

    def test_same_filesystem_always_blocks_second_copy_promotion(self):
        result = self.examine(distinct=False)
        self.assertEqual("second_copy_on_same_filesystem", result["hold_reason"])
        self.assertFalse(result["distinct_filesystem_copy_verified"])

    def test_modified_secondary_json_is_detected(self):
        (self.second / "learning.json").write_bytes(b"tampered")
        self.assertEqual("tracked_backup_hash_mismatch",
                         self.examine()["hold_reason"])

    def test_modified_secondary_private_manifest_is_detected_without_leaks(self):
        path = self.second / self.extra / "MANIFEST.json"
        obj = json.loads(path.read_text())
        obj["files"][0]["verified"] = False
        path.write_text(json.dumps(obj))
        report = self.examine()
        self.assertEqual("unverified_extra_record", report["hold_reason"])
        self.assertNotIn("raw.jpg", str(report))

    def test_missing_bundle_and_symlinked_photo_are_blocked(self):
        bundle = self.second / "operating-history.bundle"
        bundle.unlink()
        self.assertEqual("missing_or_nonregular_file", self.examine()["hold_reason"])
        shutil.copy2(self.first / bundle.name, bundle)
        photo = self.second / self.extra / "files" / "PRIVATE" / "raw.jpg"
        photo.unlink()
        try:
            photo.symlink_to(self.first / self.extra / "files" / "PRIVATE" / "raw.jpg")
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks not supported")
        self.assertEqual("symlink_in_backup", self.examine()["hold_reason"])

    def test_same_copy_and_live_repo_are_invalid_destinations(self):
        with patch.object(audit, "_filesystem_id", return_value=9):
            self.assertEqual("copy_not_separate_from_live_or_primary",
                             audit.inspect(self.repo, self.first, self.first, self.extra,
                                           expected_tracked=1, expected_extra=1)["hold_reason"])
            self.assertEqual("copy_not_separate_from_live_or_primary",
                             audit.inspect(self.repo, self.first, self.repo, self.extra,
                                           expected_tracked=1, expected_extra=1)["hold_reason"])

    def test_second_copy_ancestor_of_live_checkout_holds(self):
        # The external-copy folder has valid backup bytes, but also contains
        # the operating checkout. A different filesystem ID alone must not pass.
        external_parent = self.home / "external-parent"
        external_parent.mkdir()
        nested_live = external_parent / "live"
        shutil.copytree(self.repo, nested_live)
        shutil.copytree(self.second, external_parent, dirs_exist_ok=True)
        with patch.object(audit, "_filesystem_id",
                          side_effect=lambda p: 9 if Path(p) == external_parent else 7):
            report = audit.inspect(nested_live, self.first, external_parent, self.extra,
                                   expected_tracked=1, expected_extra=1)
        self.assertTrue(report["backup_verified"], report)
        self.assertEqual("copy_not_separate_from_live_or_primary", report["hold_reason"])
        self.assertFalse(report["distinct_filesystem_copy_verified"])
        self.assertFalse(report["install_allowed"])

    def test_bad_primary_backup_cannot_be_approved_by_good_secondary(self):
        (self.first / "learning.json").write_bytes(b"destroyed")
        result = self.examine()
        self.assertFalse(result["backup_verified"])
        self.assertEqual("tracked_backup_hash_mismatch", result["hold_reason"])

    def test_v1036_second_copy_successor_checks_exact_ancestry_bytes_and_scope(self):
        import sync_v376_successor_test_support as successor
        from unittest.mock import patch
        entry = successor.V1036_SECOND_COPY_WORKFLOW
        source = "839c5890752d39343c1345c996dd8568baeecdeb"
        watched = [entry, "unexpected-future-workflow.yml"]
        check = successor.preserve_v1036_secondary_copy_workflow_scope
        self.assertEqual(["unexpected-future-workflow.yml"], check(watched, source))
        self.assertEqual(watched, check(watched, source, head=successor.V1036_SECOND_COPY_CANDIDATE))
        self.assertEqual(watched, check(watched, "0" * 40))
        with patch.object(successor, "V1036_SECOND_COPY_SHA256", "0" * 64):
            self.assertEqual(watched, check(watched, source))
        with patch.object(successor, "V1036_SECOND_COPY_BLOB", "0" * 40):
            self.assertEqual(watched, check(watched, source))
        with patch.object(successor, "V1036_SECOND_COPY_FILES", []):
            self.assertEqual(watched, check(watched, source))
        actual_path = successor.ROOT / entry
        original_read_bytes = Path.read_bytes
        def changed_content(value):
            return b"tampered" if Path(value) == actual_path else original_read_bytes(value)
        with patch.object(Path, "read_bytes", changed_content):
            self.assertEqual(watched, check(watched, source))

    def test_strict_install_cli_returns_2_and_never_accepts_small_fixture_counts(self):
        args = ["--root", str(self.repo), "--backup", str(self.first),
                "--external-copy", str(self.second), "--extra-dir", self.extra,
                "--require-install-ready"]
        output = io.StringIO()
        with patch.object(audit, "_filesystem_id",
                          side_effect=lambda p: 9 if Path(p) == self.second else 7):
            with redirect_stdout(output):
                code = audit.main(args)
        report = json.loads(output.getvalue())
        self.assertEqual(2, code)
        self.assertFalse(report["install_allowed"])
        self.assertFalse(report["distinct_filesystem_copy_verified"])
        self.assertEqual("tracked_count_mismatch", report["hold_reason"])
        self.assertNotIn("raw.jpg", output.getvalue())

    def test_cli_rejects_any_attempt_to_override_production_inventory_counts(self):
        import contextlib
        args = ["--root", str(self.repo), "--backup", str(self.first),
                "--external-copy", str(self.second), "--extra-dir", self.extra]
        for forbidden in ("--expected-tracked", "--expected-extra"):
            with self.subTest(forbidden=forbidden), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as err:
                    audit.main(args + [forbidden, "1"])
                self.assertEqual(2, err.exception.code)


if __name__ == "__main__":
    unittest.main()

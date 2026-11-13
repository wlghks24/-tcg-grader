"""V1012: non-mutating backup and code-route verification regression tests."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from execution.tablet_migration_preflight_v1012 import inspect, main

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def run(root: Path, *args: str):
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          text=True, capture_output=True).stdout.strip()

class PreservationPreflightV1012Tests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.temp = Path(d.name)
        self.root = self.temp / "repo"
        self.backup = self.temp / "snapshot"
        self.extra = self.backup / "local-extra-demo"
        self.root.mkdir()
        self.extra.mkdir(parents=True)
        run(self.root, "init", "-b", "main")
        run(self.root, "config", "user.name", "Test")
        run(self.root, "config", "user.email", "test@example.invalid")
        run(self.root, "remote", "add", "origin", "https://github.com/wlghks24/-tcg-grader.git")
        (self.root / ".gitignore").write_text(".env\nGRADE_TRAINING_INBOX/\n")
        (self.root / "learning_store.json").write_text('{"data":"baseline"}\n')
        run(self.root, "add", ".")
        run(self.root, "commit", "-m", "base")
        run(self.root, "update-ref", "refs/remotes/origin/main", run(self.root, "rev-parse", "HEAD"))
        (self.root / "learning_store.json").write_text('{"data":"valuable-local-learning"}\n')
        shutil.copy2(self.root / "learning_store.json", self.backup / "learning_store.json")
        (self.backup / "SHA256SUMS").write_text(
            sha(self.backup / "learning_store.json") + "  learning_store.json\n")
        bundle = self.backup / "operating-history.bundle"
        run(self.root, "bundle", "create", str(bundle), "--all", "HEAD")
        (self.backup / "operating-history.bundle.sha256").write_text(
            sha(bundle) + "  operating-history.bundle\n")
        (self.root / ".env").write_bytes(b"token=do-not-print\n")
        img = self.root / "GRADE_TRAINING_INBOX" / "picture.jpg"
        img.parent.mkdir()
        img.write_bytes(b"test photo placeholder")
        rows = []
        for name in (".env", "GRADE_TRAINING_INBOX/picture.jpg"):
            destination = self.extra / "files" / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.root / name, destination)
            rows.append({"path": name, "bytes": destination.stat().st_size,
                         "sha256": sha(destination), "verified": True})
        (self.extra / "MANIFEST.json").write_text(json.dumps({
            "schema": "tablet-local-extra-preserve-v1",
            "complete": True, "files": rows,
        }))
    def checked(self):
        return inspect(self.root, self.backup, self.extra,
                       expected_tracked=1, expected_extra=2)

    def test_real_git_bundle_and_all_copy_hashes_verified_but_no_install(self):
        before = run(self.root, "rev-parse", "HEAD")
        v = self.checked()
        self.assertTrue(v["backup_verified"], v)
        self.assertEqual("BACKUPS_VERIFIED_MIGRATION_HOLD", v["status"])
        self.assertEqual("LOCAL_CACHED_MAIN_MATCH", v["code"]["code_route"])
        self.assertEqual(1, v["tracked"]["files"])
        self.assertEqual(2, v["extra"]["files"])
        self.assertFalse(v["ready_for_migration"])
        self.assertFalse(v["offdevice_copy_verified"])
        self.assertFalse(v["quiesced_consistent_snapshot_verified"])
        self.assertFalse(v["physical_tablet_verified"])
        self.assertFalse(v["writes_or_updates_performed"])
        self.assertEqual(before, run(self.root, "rev-parse", "HEAD"))

    def test_tampered_photo_copy_must_hold_without_leaking_names(self):
        (self.extra / "files" / "GRADE_TRAINING_INBOX" / "picture.jpg").write_bytes(b"tampered")
        v = self.checked()
        self.assertFalse(v["backup_verified"])
        self.assertEqual("extra_copy_hash_mismatch", v["hold_reason"])
        self.assertNotIn("picture.jpg", str(v))
        self.assertNotIn("token=do-not-print", str(v))

    def test_missing_or_modified_json_backup_holds(self):
        (self.backup / "learning_store.json").write_text('{"data":"bad"}')
        v = self.checked()
        self.assertEqual("tracked_backup_hash_mismatch", v["hold_reason"])

    def test_tampered_bundle_sha_holds(self):
        (self.backup / "operating-history.bundle.sha256").write_text("0" * 64 + "  operating-history.bundle\n")
        self.assertEqual("bundle_hash_mismatch", self.checked()["hold_reason"])

    def test_symlinked_photo_is_rejected(self):
        img = self.extra / "files" / "GRADE_TRAINING_INBOX" / "picture.jpg"
        img.unlink()
        img.symlink_to(self.root / "GRADE_TRAINING_INBOX" / "picture.jpg")
        self.assertEqual("symlink_in_backup", self.checked()["hold_reason"])

    def test_manifest_path_traversal_is_rejected(self):
        p = self.extra / "MANIFEST.json"
        j = json.loads(p.read_text())
        j["files"][0]["path"] = "../.env"
        p.write_text(json.dumps(j))
        self.assertEqual("invalid_relative_path", self.checked()["hold_reason"])

    def test_duplicate_extra_manifest_rejected(self):
        p = self.extra / "MANIFEST.json"
        j = json.loads(p.read_text())
        j["files"][1] = j["files"][0]
        p.write_text(json.dumps(j))
        self.assertEqual("duplicate_or_invalid_extra_record", self.checked()["hold_reason"])

    def test_incomplete_manifest_must_hold(self):
        p = self.extra / "MANIFEST.json"
        j = json.loads(p.read_text())
        j["complete"] = False
        p.write_text(json.dumps(j))
        self.assertEqual("extra_incomplete_or_count_mismatch", self.checked()["hold_reason"])

    def test_detached_head_preserved_and_not_reported_ready(self):
        run(self.root, "checkout", "--detach")
        v = self.checked()
        self.assertTrue(v["backup_verified"])
        self.assertEqual("DETACHED_OR_NONMAIN_HOLD", v["code"]["code_route"])
        self.assertFalse(v["ready_for_migration"])

    def test_diverged_main_is_a_hold(self):
        run(self.root, "checkout", "-b", "other", "HEAD")
        (self.root / "new.txt").write_text("extra")
        run(self.root, "add", "new.txt")
        run(self.root, "commit", "-m", "local")
        run(self.root, "checkout", "main")
        # main remains common ancestor so a real branch divergence is simulated.
        (self.root / "otherfile").write_text("local")
        run(self.root, "add", "otherfile")
        run(self.root, "commit", "-m", "main-diverge")
        # snapshot HEAD now differs, so bundle proof must also reject reuse.
        self.assertEqual("bundle_head_differs_from_operating_root", self.checked()["hold_reason"])

    def test_refuse_backup_nested_under_operating_root(self):
        self.assertEqual("backup_inside_operating_checkout", inspect(
            self.root, self.root, self.root / "nested",
            expected_tracked=1, expected_extra=2)["hold_reason"] if (self.root / "nested").mkdir() is None else "unreachable")

    def test_count_mismatch_holds_and_strict_flag_returns_two(self):
        self.assertEqual("tracked_count_mismatch", inspect(
            self.root, self.backup, self.extra,
            expected_tracked=30, expected_extra=2)["hold_reason"])
        import io
        from contextlib import redirect_stdout
        output = io.StringIO()
        with redirect_stdout(output):
            code = main(["--root", str(self.root), "--backup", str(self.backup),
                         "--extra", str(self.extra), "--expected-tracked", "1",
                         "--expected-extra", "2", "--require-ready", "--json"])
        self.assertEqual(2, code)
        self.assertFalse(json.loads(output.getvalue())["ready_for_migration"])

if __name__ == "__main__":
    unittest.main()

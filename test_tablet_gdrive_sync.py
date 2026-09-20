#!/usr/bin/env python3
import datetime as dt
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest import mock

import tablet_gdrive_sync as sync
import tablet_gdrive_sync_hardening as hardening


ROOT = Path(__file__).resolve().parent


class TabletGDriveSyncTests(unittest.TestCase):
    def build_fixture(self):
        td = Path(tempfile.mkdtemp())
        src = td / "src"
        src.mkdir()
        files = []
        for i, name in enumerate(sync.OUTPUTS):
            p = src / name
            p.write_text(json.dumps({"name": name, "i": i}), encoding="utf-8")
            files.append({"name": name, "size": p.stat().st_size, "sha256": sync.sha256(p)})
        bundle = td / "TCG_VERIFIED_20260919T000000Z_testrun01.tar.gz"
        with tarfile.open(bundle, "w:gz") as tf:
            for name in sync.OUTPUTS:
                tf.add(src / name, arcname=name)
        manifest = {
            "schema_version": sync.SCHEMA,
            "repository": sync.REPO,
            "source": "chatgpt_automation",
            "run_id": "testrun01",
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "main_sha": "a" * 40,
            "bundle": {
                "name": bundle.name,
                "size": bundle.stat().st_size,
                "sha256": sync.sha256(bundle),
            },
            "files": files,
        }
        mp = td / "manifest_20260919T000000Z_testrun01.json"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        return td, bundle, mp, manifest

    def build_backup(self, root: Path, prefix: str = "good") -> Path:
        backup = root / "last_good" / "testrun01"
        backup.mkdir(parents=True)
        hashes = {}
        for name in sync.OUTPUTS:
            path = backup / name
            path.write_text(json.dumps({"source": prefix, "name": name}), encoding="utf-8")
            hashes[name] = sync.sha256(path)
        (backup / "backup_manifest.json").write_text(
            json.dumps({"sha256": hashes}), encoding="utf-8"
        )
        return backup

    def build_repo(self, root: Path, prefix: str = "bad") -> Path:
        repo = root / "repo"
        repo.mkdir()
        for name in sync.OUTPUTS:
            (repo / name).write_text(json.dumps({"source": prefix, "name": name}), encoding="utf-8")
        return repo

    def test_valid_manifest_and_exact_17_bundle(self):
        td, bundle, mp, _ = self.build_fixture()
        loaded = sync.load_manifest(mp)
        stage = td / "stage"
        stage.mkdir()
        sync.extract_bundle(bundle, stage, loaded)
        self.assertEqual(set(p.name for p in stage.iterdir()), set(sync.OUTPUTS))

    def test_rejects_path_traversal(self):
        td, _, _, manifest = self.build_fixture()
        bad = td / "bad.tar.gz"
        with tarfile.open(bad, "w:gz") as tf:
            info = tarfile.TarInfo("../evil.json")
            raw = b"{}"
            info.size = len(raw)
            tf.addfile(info, io.BytesIO(raw))
        stage = td / "bad-stage"
        stage.mkdir()
        with self.assertRaises(ValueError):
            sync.extract_bundle(bad, stage, manifest)

    def test_rejects_partial_manifest(self):
        _, _, mp, manifest = self.build_fixture()
        manifest["files"] = manifest["files"][:-1]
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValueError):
            sync.load_manifest(mp)

    def test_rejects_wrong_source_and_repo(self):
        _, _, mp, manifest = self.build_fixture()
        manifest["source"] = "unknown"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValueError):
            sync.load_manifest(mp)
        manifest["source"] = "chatgpt_automation"
        manifest["repository"] = "other/repo"
        mp.write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaises(ValueError):
            sync.load_manifest(mp)

    def test_remote_name_rejects_newline(self):
        with self.assertRaises(ValueError):
            sync.safe_remote_name("gdrive\n--config=x")
        self.assertEqual(sync.safe_remote_name("gdrive:"), "gdrive")

    def test_installer_polls_exactly_every_12_hours(self):
        installer = (ROOT / "TABLET_GDRIVE_SYNC_INSTALL.sh").read_text(encoding="utf-8")
        self.assertIn('CRON_LINE="0 8,20 * * *', installer)
        self.assertNotIn('CRON_LINE="*/15 * * * *', installer)
        self.assertIn('주기: 12시간마다 1회', installer)

    def test_installer_does_not_run_unscheduled_full_sync_by_default(self):
        installer = (ROOT / "TABLET_GDRIVE_SYNC_INSTALL.sh").read_text(encoding="utf-8")
        self.assertIn('TCG_GDRIVE_SYNC_RUN_NOW', installer)
        self.assertIn('if [ "${TCG_GDRIVE_SYNC_RUN_NOW:-0}" = "1" ]', installer)
        self.assertNotIn('echo "[검증] 첫 동기화 확인"', installer)

    def test_boot_recovery_is_ordered_and_cron_boot_has_no_permanent_wakelock(self):
        installer = (ROOT / "TABLET_GDRIVE_SYNC_INSTALL.sh").read_text(encoding="utf-8")
        self.assertIn('BOOT_RECOVERY_FILE="$BOOT_DIR/00_TCG_GDRIVE_RECOVERY.sh"', installer)
        recovery_block = installer.split('cat > "$BOOT_RECOVERY_FILE" <<EOF', 1)[1].split('EOF', 1)[0]
        self.assertIn('--recover-only', recovery_block)
        cron_block = installer.split('cat > "$BOOT_CRON_FILE" <<EOF', 1)[1].split('EOF', 1)[0]
        self.assertIn('crond', cron_block)
        self.assertNotIn('termux-wake-lock', cron_block)
        self.assertNotIn('TABLET_GDRIVE_SYNC.sh', cron_block)

    def test_wrapper_scopes_wakelock_to_one_sync_and_uses_hardened_runner(self):
        wrapper = (ROOT / "TABLET_GDRIVE_SYNC.sh").read_text(encoding="utf-8")
        perf_runtime = (ROOT / "tablet_gdrive_sync_perf_v262.py").read_text(encoding="utf-8")
        self.assertIn('termux-wake-lock', wrapper)
        self.assertIn('termux-wake-unlock', wrapper)
        self.assertIn('tablet_gdrive_sync_perf_v262.py', wrapper)
        self.assertNotIn('python tablet_gdrive_sync_hardening_contextual.py', wrapper)
        self.assertIn('import tablet_gdrive_sync_hardening as hard', perf_runtime)
        self.assertIn('import tablet_gdrive_sync_hardening_contextual as contextual', perf_runtime)
        self.assertIn('rc = contextual.main()', perf_runtime)
        self.assertIn('return rc', perf_runtime)
        self.assertNotIn('wrapper.lock', wrapper)

    def test_runner_lock_is_kernel_released_not_stale_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            first = hardening.acquire_runner_lock(state)
            self.assertIsNotNone(first)
            second = hardening.acquire_runner_lock(state)
            self.assertIsNone(second)
            hardening.release_runner_lock(first)
            third = hardening.acquire_runner_lock(state)
            self.assertIsNotNone(third)
            hardening.release_runner_lock(third)

    def test_stale_legacy_sync_lock_directory_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp)
            legacy = state / hardening.LEGACY_LOCK
            legacy.mkdir()
            (legacy / "leftover").write_text("crash", encoding="utf-8")
            hardening.remove_legacy_lock(state)
            self.assertFalse(legacy.exists())

    def test_existing_backup_is_rotated_instead_of_blocking_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            backup = Path(tmp) / "testrun01"
            backup.mkdir()
            (backup / "old").write_text("old", encoding="utf-8")
            rotated = hardening.rotate_existing_backup(backup)
            self.assertIsNotNone(rotated)
            self.assertFalse(backup.exists())
            self.assertTrue((rotated / "old").is_file())

    def test_backup_hash_tamper_is_detected_before_rollback(self):
        with tempfile.TemporaryDirectory() as tmp:
            backup = self.build_backup(Path(tmp))
            hardening.verify_backup(backup)
            (backup / sync.OUTPUTS[0]).write_text("tampered", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                hardening.verify_backup(backup)

    def test_healthy_server_without_launcher_pid_fails_closed(self):
        with mock.patch.object(hardening.core, "read_launcher_pid", return_value=None), \
             mock.patch.object(hardening.core, "health_ok", return_value=True):
            with self.assertRaises(RuntimeError):
                hardening.hardened_stop_server(Path("."))

    def test_inflight_crash_transaction_restores_verified_last_good(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state"
            repo = self.build_repo(root, "partial")
            backup = self.build_backup(state, "good")
            hardening.write_transaction(state, repo, backup)
            with mock.patch.object(hardening.core, "health_ok", return_value=False):
                recovered = hardening.recover_incomplete(repo, state)
            self.assertTrue(recovered)
            self.assertFalse(hardening.transaction_path(state).exists())
            for name in sync.OUTPUTS:
                data = json.loads((repo / name).read_text(encoding="utf-8"))
                self.assertEqual(data["source"], "good")


if __name__ == "__main__":
    unittest.main()

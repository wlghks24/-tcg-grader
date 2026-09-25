#!/usr/bin/env python3
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import tablet_gdrive_sync as core
import tablet_gdrive_sync_hardening as hard
import tablet_gdrive_sync_perf_v262 as perf


class _Response:
    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, _limit=-1):
        return self._body


class TabletGDriveSyncPerfV262Tests(unittest.TestCase):
    def test_manifest_discovery_is_bounded_to_fresh_remote_window(self):
        remote_output = "\n".join([
            "manifest_20260920T000000Z_run00002.json",
            "not-a-manifest.json",
            "manifest_20260919T000000Z_run00001.json",
            "manifest_20260920T000000Z_run00002.json",
        ])
        with mock.patch.object(perf.core, "run", return_value=remote_output) as run:
            names = perf.bounded_list_manifests("gdrive", "TCG_Grader_Sync")
        self.assertEqual(names, [
            "manifest_20260919T000000Z_run00001.json",
            "manifest_20260920T000000Z_run00002.json",
        ])
        command = run.call_args.args[0]
        self.assertIn("--max-age", command)
        self.assertEqual(command[command.index("--max-age") + 1], perf.REMOTE_MANIFEST_MAX_AGE)
        self.assertEqual(run.call_args.kwargs["timeout"], 30)

    def test_health_probe_is_single_bounded_identity_checked_request(self):
        response = _Response(b'{"ok":true,"service":"TCG v109 Updater"}')
        with mock.patch.object(perf.urllib.request, "urlopen", return_value=response) as urlopen:
            self.assertTrue(perf.fast_health_ok())
        self.assertEqual(urlopen.call_count, 1)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://127.0.0.1:8765/api/health")
        self.assertEqual(urlopen.call_args.kwargs["timeout"], perf.HEALTH_TIMEOUT_SECONDS)

        oversized = _Response(b"x" * (64 * 1024 + 1))
        with mock.patch.object(perf.urllib.request, "urlopen", return_value=oversized):
            self.assertFalse(perf.fast_health_ok())
        with mock.patch.object(perf.urllib.request, "urlopen", return_value=_Response(b'{"ok":true}')):
            self.assertFalse(perf.fast_health_ok())
        with mock.patch.object(perf.urllib.request, "urlopen", return_value=_Response(b'{"ok":true,"service":"other"}')):
            self.assertFalse(perf.fast_health_ok())

    def test_restore_reads_backup_manifest_once_after_verified_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            backup = root / "backup"
            repo.mkdir()
            backup.mkdir()
            digest = "a" * 64
            (backup / "backup_manifest.json").write_text(
                json.dumps({"sha256": {name: digest for name in core.OUTPUTS}}),
                encoding="utf-8",
            )
            hashes = {name: digest for name in core.OUTPUTS}
            with mock.patch.object(perf.hard, "verify_backup", return_value=hashes) as verify, \
                 mock.patch.object(perf.hard, "_ORIGINAL_RESTORE_BACKUP") as restore, \
                 mock.patch.object(perf.core, "sha256", return_value=digest), \
                 mock.patch.object(perf.json, "loads", side_effect=AssertionError("manifest must not be reparsed")):
                perf.optimized_hardened_restore_backup(repo, backup)
            verify.assert_called_once_with(backup)
            restore.assert_called_once_with(repo, backup)

    def test_state_retention_is_bounded_and_preserves_inflight_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            receipts = state / "receipts"
            completed = state / "completed"
            last_good = state / "last_good"
            receipts.mkdir(parents=True)
            completed.mkdir()
            last_good.mkdir()

            for i in range(70):
                receipt = receipts / f"TABLET_SYNC_RECEIPT_run{i:03d}.json"
                receipt.write_text("{}", encoding="utf-8")
                sent = receipt.with_suffix(receipt.suffix + ".sent")
                sent.write_text("sent\n", encoding="utf-8")
                stamp = 1_700_000_000 + i
                os.utime(receipt, (stamp, stamp))
                os.utime(sent, (stamp, stamp))

            for i in range(140):
                marker = completed / f"run{i:03d}"
                marker.write_text("manifest\n", encoding="utf-8")
                stamp = 1_700_100_000 + i
                os.utime(marker, (stamp, stamp))

            backups = []
            for i in range(12):
                folder = last_good / f"run{i:03d}"
                folder.mkdir()
                (folder / "dummy").write_text("ok", encoding="utf-8")
                stamp = 1_700_200_000 + i
                os.utime(folder, (stamp, stamp))
                backups.append(folder)

            # Preserve the oldest backup even though retention would otherwise
            # delete it: it is the rollback source for an active transaction.
            repo = Path(tmp) / "repo"
            repo.mkdir()
            hard.write_transaction(state, repo, backups[0])

            result = perf.prune_state(state)
            self.assertEqual(result["patch"], perf.PATCH_ID)
            self.assertEqual(len(list(receipts.glob("TABLET_SYNC_RECEIPT_*.json"))), perf.RECEIPT_KEEP)
            self.assertEqual(len(list(receipts.glob("TABLET_SYNC_RECEIPT_*.json.sent"))), perf.RECEIPT_KEEP)
            self.assertEqual(len([p for p in completed.iterdir() if p.is_file()]), perf.COMPLETED_KEEP)
            remaining = [p.resolve() for p in last_good.iterdir() if p.is_dir()]
            self.assertIn(backups[0].resolve(), remaining)
            self.assertLessEqual(len(remaining), perf.LAST_GOOD_KEEP + 1)

    def test_runtime_patch_keeps_contextual_hardening_stack_and_only_rebinds_hotspots(self):
        original_list = perf.core.list_manifests
        original_health = perf.core.health_ok
        original_restore = perf.hard.hardened_restore_backup
        try:
            perf.apply_runtime_patch()
            self.assertIs(perf.core.list_manifests, perf.bounded_list_manifests)
            self.assertIs(perf.core.health_ok, perf.fast_health_ok)
            self.assertIs(perf.hard.hardened_restore_backup, perf.optimized_hardened_restore_backup)
        finally:
            perf.core.list_manifests = original_list
            perf.core.health_ok = original_health
            perf.hard.hardened_restore_backup = original_restore


if __name__ == "__main__":
    unittest.main()

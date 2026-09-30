#!/usr/bin/env python3
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

import tablet_gdrive_sync as core
import tablet_gdrive_sync_perf_v262 as perf


class ReceiptCompletionRegressionTests(unittest.TestCase):
    RUN_ID = "run00001"
    MANIFEST_NAME = "manifest_20260930T000000Z_run00001.json"
    MAIN_SHA = "a" * 40
    DIGEST = "d" * 64

    def _manifest(self):
        return {
            "run_id": self.RUN_ID,
            "main_sha": self.MAIN_SHA,
            "bundle": {
                "name": f"TCG_VERIFIED_20260930T000000Z_{self.RUN_ID}.tar.gz",
                "size": len(b"bundle"),
                "sha256": self.DIGEST,
            },
            "files": [
                {"name": name, "size": len(b"{}"), "sha256": self.DIGEST}
                for name in core.OUTPUTS
            ],
        }

    def _copyto(self, _remote, _remote_path, local_path):
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        if local_path.name == self.MANIFEST_NAME:
            local_path.write_text("{}", encoding="utf-8")
        else:
            local_path.write_bytes(b"bundle")

    def _apply_stage(self, repo, _stage):
        for name in core.OUTPUTS:
            (repo / name).write_bytes(b"{}")

    def _write_receipt(self, events, state, manifest, status, details):
        self.assertEqual(manifest["run_id"], self.RUN_ID)
        path = state / "receipts" / f"TABLET_SYNC_RECEIPT_{self.RUN_ID}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        events.append(("receipt", status, dict(details)))
        return path

    def _common_patches(self, root, repo, manifest, events, *, apply_side_effect=None):
        real_atomic = perf._atomic_write_text

        def record_atomic(path, text):
            if path.name.endswith(".sent"):
                events.append(("sent", path.name))
            elif path.parent.name == "completed":
                events.append(("completed", path.name))
            return real_atomic(path, text)

        def apply_stage(repo_arg, stage_arg):
            if apply_side_effect is not None:
                raise apply_side_effect
            self._apply_stage(repo_arg, stage_arg)

        return (
            mock.patch.object(perf.Path, "home", return_value=root),
            mock.patch.object(perf.core, "list_manifests", return_value=[self.MANIFEST_NAME]),
            mock.patch.object(perf.core, "rclone_copyto", side_effect=self._copyto),
            mock.patch.object(perf.core, "load_manifest", return_value=manifest),
            mock.patch.object(perf.core, "ensure_exact_main", return_value=None),
            mock.patch.object(perf.core, "sha256", return_value=self.DIGEST),
            mock.patch.object(perf.core, "extract_bundle", return_value=None),
            mock.patch.object(perf.core, "run_project_gates", return_value=None),
            mock.patch.object(perf.core, "backup_current", return_value=None),
            mock.patch.object(perf.core, "apply_stage", side_effect=apply_stage),
            mock.patch.object(perf.core, "start_server", return_value=None),
            mock.patch.object(perf, "_atomic_write_text", side_effect=record_atomic),
        )

    def test_full_sync_orders_receipt_upload_sent_then_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            manifest = self._manifest()
            events = []

            patches = self._common_patches(root, repo, manifest, events)
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
                 patches[6], patches[7], patches[8], patches[9], patches[10], patches[11], \
                 mock.patch.object(perf.core, "health_ok", side_effect=[False, True]), \
                 mock.patch.object(perf.core, "runtime_matches_main", return_value=True), \
                 mock.patch.object(
                     perf.core,
                     "write_receipt",
                     side_effect=lambda state, m, status, details: self._write_receipt(
                         events, state, m, status, details
                     ),
                 ), \
                 mock.patch.object(
                     perf.core,
                     "rclone_upload",
                     side_effect=lambda _remote, _receipt, _path: events.append(("upload", _path)),
                 ):
                rc = perf.sync_once_receipt_fail_closed(repo, "gdrive", "TCG_Grader_Sync")

            self.assertEqual(rc, 0)
            kinds = [row[0] for row in events]
            self.assertEqual(kinds, ["receipt", "upload", "sent", "completed"])
            receipt_event = events[0]
            self.assertEqual(receipt_event[1], "TABLET_SYNC_OK")
            self.assertTrue(receipt_event[2]["runtime_health"])
            self.assertTrue(receipt_event[2]["runtime_main_sha_verified"])
            self.assertEqual(receipt_event[2]["file_count"], 17)
            self.assertEqual(len(core.OUTPUTS), 17)

            state = root / ".local" / "state" / "tcg-grader" / "gdrive-sync"
            receipt = state / "receipts" / f"TABLET_SYNC_RECEIPT_{self.RUN_ID}.json"
            sent = receipt.with_suffix(receipt.suffix + ".sent")
            completed = state / "completed" / self.RUN_ID
            self.assertTrue(receipt.is_file())
            self.assertTrue(sent.is_file())
            self.assertEqual(completed.read_text(encoding="utf-8"), self.MANIFEST_NAME + "\n")

    def test_full_sync_upload_failure_leaves_no_sent_or_completed_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            manifest = self._manifest()
            events = []
            upload_error = subprocess.CalledProcessError(1, ["rclone", "copyto"])

            patches = self._common_patches(root, repo, manifest, events)
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
                 patches[6], patches[7], patches[8], patches[9], patches[10], patches[11], \
                 mock.patch.object(perf.core, "health_ok", side_effect=[False, True]), \
                 mock.patch.object(perf.core, "runtime_matches_main", return_value=True), \
                 mock.patch.object(
                     perf.core,
                     "write_receipt",
                     side_effect=lambda state, m, status, details: self._write_receipt(
                         events, state, m, status, details
                     ),
                 ), \
                 mock.patch.object(perf.core, "rclone_upload", side_effect=upload_error) as upload:
                with self.assertRaises(subprocess.CalledProcessError):
                    perf.sync_once_receipt_fail_closed(repo, "gdrive", "TCG_Grader_Sync")

            upload.assert_called_once()
            state = root / ".local" / "state" / "tcg-grader" / "gdrive-sync"
            receipt = state / "receipts" / f"TABLET_SYNC_RECEIPT_{self.RUN_ID}.json"
            sent = receipt.with_suffix(receipt.suffix + ".sent")
            completed = state / "completed" / self.RUN_ID
            self.assertTrue(receipt.is_file())
            self.assertFalse(sent.exists())
            self.assertFalse(completed.exists())
            self.assertEqual([row[0] for row in events], ["receipt"])

    def test_rollback_preserves_apply_error_when_receipt_upload_also_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            repo.mkdir()
            manifest = self._manifest()
            events = []
            apply_error = RuntimeError("apply exploded")
            upload_error = subprocess.CalledProcessError(1, ["rclone", "copyto"])

            patches = self._common_patches(
                root, repo, manifest, events, apply_side_effect=apply_error
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], \
                 patches[6], patches[7], patches[8], patches[9], patches[10], patches[11], \
                 mock.patch.object(perf.core, "health_ok", return_value=False), \
                 mock.patch.object(perf.core, "restore_backup", return_value=None) as restore, \
                 mock.patch.object(
                     perf.core,
                     "write_receipt",
                     side_effect=lambda state, m, status, details: self._write_receipt(
                         events, state, m, status, details
                     ),
                 ), \
                 mock.patch.object(perf.core, "rclone_upload", side_effect=upload_error) as upload:
                with self.assertRaisesRegex(RuntimeError, "^apply exploded$"):
                    perf.sync_once_receipt_fail_closed(repo, "gdrive", "TCG_Grader_Sync")

            restore.assert_called_once()
            upload.assert_called_once()
            self.assertEqual(events[0][0], "receipt")
            self.assertEqual(events[0][1], "FAILED_ROLLED_BACK")
            self.assertIn("RuntimeError: apply exploded", events[0][2]["error"])

            state = root / ".local" / "state" / "tcg-grader" / "gdrive-sync"
            receipt = state / "receipts" / f"TABLET_SYNC_RECEIPT_{self.RUN_ID}.json"
            sent = receipt.with_suffix(receipt.suffix + ".sent")
            completed = state / "completed" / self.RUN_ID
            self.assertTrue(receipt.is_file())
            self.assertFalse(sent.exists())
            self.assertFalse(completed.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

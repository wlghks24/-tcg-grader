"""Negative-path regression: no real Android process or data mutation."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from execution.tablet_delivery_status_v1005 import evaluate

SHA_A = "a" * 40
SHA_B = "b" * 40
NOW = datetime(2026, 11, 11, 7, 0, tzinfo=timezone.utc)

class DeliveryTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.root = Path(d.name) / "repo"
        self.root.mkdir()
        self.state = Path(d.name) / "scheduled"
        self.state.mkdir()
        self.git = {
            "sha_full": SHA_A, "branch": "main", "origin_main": SHA_A,
            "origin_url": "https://github.com/wlghks24/-tcg-grader.git",
        }
        self.health = {"ok": True}
        self.runtime = {"ok": True, "running_build_sha": SHA_A}
        self.write("status.env", "RESULT=UPDATED\\nLOCAL_SHA=" + SHA_A +
                   "\\nREMOTE_SHA=" + SHA_A + "\\nLAST_CHECK=2026-11-11T16:00:00+0900\\n")

    def write(self, name, value):
        (self.state / name).write_text(value, encoding="utf-8")

    def result(self, **kw):
        return evaluate(self.root, kw.get("git", self.git),
                        kw.get("health", self.health),
                        kw.get("runtime", self.runtime),
                        now=kw.get("now", NOW), state_root=self.state)

    def test_valid_local_main_and_http_are_separate_from_reboot(self):
        result = self.result()
        self.assertEqual(result["code_update_status"], "LOCAL_MAIN_CHECK_VERIFIED")
        self.assertEqual(result["runtime_status"], "RUNNING_SHA_VERIFIED_LOCAL_HTTP")
        self.assertFalse(result["ready_for_device_readback"])
        self.assertFalse(result["physical_tablet_verified"])
        self.assertFalse(result["reboot_verified"])

    def test_updated_disk_old_server_holds(self):
        result = self.result(runtime={"ok": False, "running_build_sha": SHA_B})
        self.assertEqual(result["runtime_status"], "RUNNING_SHA_MISMATCH")

    def test_failed_health_never_counts_as_running(self):
        result = self.result(health={"ok": False})
        self.assertEqual(result["runtime_status"], "RUNNING_SHA_UNVERIFIED")

    def test_stale_receipt_and_unexpected_branch_rejected(self):
        self.assertEqual(self.result(now=NOW + timedelta(days=3))["code_update_status"], "MAIN_UPDATE_UNVERIFIED")
        self.assertEqual(self.result(git={**self.git, "branch": "feature"})["code_update_status"], "MAIN_UPDATE_UNVERIFIED")

    def test_wrong_origin_and_stale_remote_ref_rejected(self):
        self.assertEqual(self.result(git={**self.git, "origin_main": SHA_B})["code_update_status"], "MAIN_UPDATE_UNVERIFIED")
        self.assertEqual(self.result(git={**self.git, "origin_url": "https://github.com/evil/x.git"})["code_update_status"], "MAIN_UPDATE_UNVERIFIED")

    def test_explicit_hold_remains_hold(self):
        self.write("status.env", "RESULT=FETCH_FAILED\\nLOCAL_SHA=" + SHA_A +
                   "\\nREMOTE_SHA=" + SHA_A + "\\nLAST_CHECK=2026-11-11T16:00:00+0900\\n")
        self.assertEqual(self.result()["code_update_status"], "MAIN_UPDATE_HOLD")

    def test_fake_pid_and_heartbeat_cannot_claim_scheduler(self):
        self.write("boot-loop.pid", "PID=99999999\\nVERSION=daily-2300-kst-v3\\n")
        self.write("boot-heartbeat.env", "BOOT_LOOP_PID=99999999\\nBOOT_LOOP_VERSION=daily-2300-kst-v3\\n"
                   "BOOT_LOOP_HEARTBEAT_AT=2026-11-11T16:00:00+0900\\nROOT=" + str(self.root) + "\\n")
        self.assertEqual(self.result()["scheduler_status"], "LOOP_NOT_VERIFIED")

    def test_symlinked_or_oversize_status_is_ignored(self):
        path = self.state / "status.env"
        path.write_text("x" * 8193)
        self.assertEqual(self.result()["code_update_status"], "MAIN_UPDATE_UNVERIFIED")
        path.unlink()
        other = self.state / "untrusted"
        other.write_text("RESULT=UPDATED\\n")
        path.symlink_to(other)
        self.assertEqual(self.result()["code_update_status"], "MAIN_UPDATE_UNVERIFIED")

    def test_env_metacharacters_are_not_executed(self):
        self.write("status.env", "RESULT=$(touch exploit)\\n")
        self.assertEqual(self.result()["code_update_status"], "MAIN_UPDATE_UNVERIFIED")
        self.assertFalse((self.root / "exploit").exists())

    def test_probe_contains_delivery_without_writing_or_starting(self):
        import tablet_runtime_probe as probe
        with patch.object(probe, "git_state", return_value=self.git), \
             patch.object(probe, "health_probe", return_value={"ok": False}):
            report = probe.build_report(self.root, probe_network=False)
        self.assertIn("delivery", report)
        self.assertEqual(report["delivery"]["runtime_status"], "RUNNING_SHA_UNVERIFIED")
        self.assertFalse(report["delivery"]["physical_tablet_verified"])

if __name__ == "__main__":
    unittest.main()

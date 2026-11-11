"""Fail-closed delivery evidence tests; no process starts or device actions."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from execution.tablet_delivery_status_v1005 import _read_env, evaluate

SHA_A = "a" * 40
SHA_B = "b" * 40
NOW = datetime(2026, 11, 11, 7, 0, tzinfo=timezone.utc)


class DeliveryEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        self.state = Path(self.tmp.name) / "state"
        self.state.mkdir()
        self.git = {"sha_full": SHA_A, "branch": "main", "origin_main": SHA_A, "origin_url": "https://github.com/wlghks24/-tcg-grader.git"}
        self.health = {"ok": True}
        self.runtime = {"ok": True, "running_build_sha": SHA_A}
        self.write("status.env", "RESULT=UPDATED\nLOCAL_SHA=" + SHA_A + "\nREMOTE_SHA=" + SHA_A + "\nLAST_CHECK=2026-11-11T16:00:00+0900\n")

    def write(self, name, content):
        (self.state / name).write_text(content, encoding="utf-8")

    def result(self, **kw):
        return evaluate(self.root, kw.get("git", self.git), kw.get("health", self.health),
                        kw.get("runtime", self.runtime), state_root=self.state, now=kw.get("now", NOW))

    def test_matching_local_code_and_http_do_not_claim_reboot_or_install(self):
        r = self.result()
        self.assertEqual(r["code_update_status"], "LOCAL_MAIN_CHECK_VERIFIED")
        self.assertEqual(r["runtime_status"], "RUNNING_SHA_VERIFIED_LOCAL_HTTP")
        self.assertEqual(r["scheduler_status"], "LOOP_NOT_VERIFIED")
        self.assertFalse(r["ready_for_device_readback"])
        self.assertFalse(r["physical_tablet_verified"])
        self.assertFalse(r["reboot_verified"])

    def test_disk_updated_but_running_server_old_is_blocked(self):
        r = self.result(runtime={"ok": False, "running_build_sha": SHA_B})
        self.assertEqual(r["runtime_status"], "RUNNING_SHA_MISMATCH")
        self.assertFalse(r["ready_for_device_readback"])

    def test_lack_of_successful_http_cannot_pass(self):
        r = self.result(health={"ok": None}, runtime={"ok": True, "running_build_sha": SHA_A})
        self.assertEqual(r["runtime_status"], "RUNNING_SHA_UNVERIFIED")

    def test_stale_success_and_false_main_are_rejected(self):
        r = self.result(now=NOW + timedelta(days=3))
        self.assertEqual(r["code_update_status"], "MAIN_UPDATE_UNVERIFIED")
        r = self.result(git={**self.git, "branch": "feature"})
        self.assertEqual(r["code_update_status"], "MAIN_UPDATE_UNVERIFIED")

    def test_wrong_remote_and_spoofed_origin_are_rejected(self):
        r = self.result(git={**self.git, "origin_main": SHA_B})
        self.assertEqual(r["code_update_status"], "MAIN_UPDATE_UNVERIFIED")
        r = self.result(git={**self.git, "origin_url": "https://github.com/attacker/repo.git"})
        self.assertEqual(r["code_update_status"], "MAIN_UPDATE_UNVERIFIED")

    def test_update_failure_does_not_become_success(self):
        self.write("status.env", "RESULT=LOCAL_CHANGES_HOLD\nLOCAL_SHA=" + SHA_A + "\nREMOTE_SHA=" + SHA_A + "\nLAST_CHECK=2026-11-11T16:00:00+0900\n")
        self.assertEqual(self.result()["code_update_status"], "MAIN_UPDATE_HOLD")

    def test_env_payload_is_parsed_as_data_not_executed(self):
        self.write("status.env", "RESULT=$(touch malicious)\nLOCAL_SHA=" + SHA_A + "\n")
        self.assertEqual(_read_env(self.state / "status.env")["RESULT"], "$(touch malicious)")
        self.assertFalse((self.root / "malicious").exists())
        self.assertEqual(self.result()["code_update_status"], "MAIN_UPDATE_UNVERIFIED")

    def test_symlinked_update_status_is_not_trusted(self):
        (self.state / "status.env").unlink()
        original = Path(self.tmp.name) / "external"
        original.write_text("RESULT=UPDATED\n")
        (self.state / "status.env").symlink_to(original)
        self.assertEqual(self.result()["code_update_status"], "MAIN_UPDATE_UNVERIFIED")

    def test_fake_heartbeat_pid_never_claims_running(self):
        self.write("boot-loop.pid", "PID=99999999\nVERSION=daily-2300-kst-v3\n")
        self.write("boot-heartbeat.env", "BOOT_LOOP_PID=99999999\nBOOT_LOOP_VERSION=daily-2300-kst-v3\nBOOT_LOOP_HEARTBEAT_AT=2026-11-11T16:00:00+0900\nROOT=" + str(self.root) + "\n")
        self.assertEqual(self.result()["scheduler_status"], "LOOP_NOT_VERIFIED")

    def test_runtime_probe_includes_read_only_delivery_verdict(self):
        from tablet_runtime_probe import build_report
        report = build_report(self.root, probe_health=False, probe_network=False)
        self.assertIn("delivery", report)
        self.assertEqual(report["delivery"]["code_update_status"], "MAIN_UPDATE_UNVERIFIED")
        self.assertEqual(report["delivery"]["runtime_status"], "RUNNING_SHA_UNVERIFIED")
        self.assertFalse(report["delivery"]["physical_tablet_verified"])

    def test_boot_script_cannot_be_counted_as_reboot_evidence(self):
        self.assertFalse(self.result()["reboot_verified"])

    def test_invalid_or_future_timestamp_is_not_fresh(self):
        self.write("status.env", "RESULT=UPDATED\nLOCAL_SHA=" + SHA_A + "\nREMOTE_SHA=" + SHA_A + "\nLAST_CHECK=2026-11-11T23:00:00+0900\n")
        self.assertEqual(self.result()["code_update_status"], "MAIN_UPDATE_UNVERIFIED")

    def test_oversized_scheduler_file_not_trusted(self):
        self.write("status.env", "x" * 8193)
        self.assertEqual(self.result()["code_update_status"], "MAIN_UPDATE_UNVERIFIED")


if __name__ == "__main__":
    unittest.main()

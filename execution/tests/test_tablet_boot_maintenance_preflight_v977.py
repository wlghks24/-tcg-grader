"""Offline Boot protocol gate tests: no live device or process control."""
import tempfile
import unittest
from pathlib import Path
from execution.tablet_boot_maintenance_preflight_v977 import inspect, PROTOCOL, PAUSE, ACK


class BootGateTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        (self.repo / ".git").mkdir()
        self.boot = self.root / "TCG_AUTO_START.sh"

    def test_legacy_boot_is_hold(self):
        self.boot.write_text("#!/bin/bash\nwhile true; do sleep 60; done\n")
        result = inspect(self.repo, self.boot)
        self.assertIn("BOOT_PROTOCOL_NOT_PRESENT", result["reasons"])
        self.assertFalse(result["files_written"])

    def test_missing_boot_is_hold(self):
        result = inspect(self.repo, self.boot)
        self.assertIn("BOOT_SCRIPT_NOT_REGULAR", result["reasons"])

    def test_symlink_boot_is_hold(self):
        target = self.root / "original"
        target.write_text(PROTOCOL + PAUSE + ACK)
        self.boot.symlink_to(target)
        self.assertIn("BOOT_SCRIPT_NOT_REGULAR", inspect(self.repo, self.boot)["reasons"])

    def test_markers_do_not_claim_runtime_safe(self):
        self.boot.write_text("\n".join((PROTOCOL, PAUSE, ACK)))
        result = inspect(self.repo, self.boot)
        self.assertTrue(result["protocol_marker_present"])
        self.assertIn("BOOT_PAUSE_ACK_RUNTIME_NOT_VERIFIED", result["reasons"])
        self.assertEqual(result["status"], "HOLD_NO_DEVICE_ACTION")
        self.assertFalse(result["installation_completed"])


if __name__ == "__main__":
    unittest.main()

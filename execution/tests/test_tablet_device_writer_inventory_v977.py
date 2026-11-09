"""V977 process inventory tests: fake procfs only, no device signals."""
from pathlib import Path
import tempfile
import unittest
from execution import tablet_device_writer_inventory_v977 as inv


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "live"
        self.repo.mkdir()
        (self.repo / ".git").mkdir()
        self.proc = self.root / "proc"
        self.proc.mkdir()

    def process(self, pid, ppid, cmd, cwd=None):
        p = self.proc / str(pid)
        p.mkdir()
        (p / "cmdline").write_bytes(cmd.encode() + bytes([0]))
        # 19 fields after comm precede starttime at index 19
        tail = ["S", str(ppid)] + ["0"] * 17 + ["12345"] + ["0"] * 4
        (p / "stat").write_text(str(pid) + " (python) " + " ".join(tail))
        (p / "cwd").symlink_to(cwd or self.repo, target_is_directory=True)

    def test_missing_supervisor_and_writers_hold(self):
        result = inv.inventory(self.repo, self.proc)
        self.assertEqual(result["status"], "HOLD_NO_DEVICE_ACTION")
        self.assertFalse(result["signals_sent"])
        self.assertIn("REQUIRED_ROLES_NOT_UNIQUELY_VERIFIED", result["reasons"])

    def test_orphan_and_boot_are_hard_hold(self):
        self.process(7880, 6257, "bash /home/.termux/boot/TCG_AUTO_START.sh")
        self.process(896, 26217, "bash execution/start_tablet_unified_v897.sh")
        self.process(1363, 896, "python graded_photo_manual_pair_queue.py --watch")
        self.process(1365, 896, "python verified_slab_raw_learning_v155.py --watch")
        self.process(1366, 896, "python -m execution.tablet_unified_runtime_v889")
        self.process(9951, 1, "python verified_slab_training_archive_v152.py --watch")
        lock = self.repo / ".tcg_android_start.lock"
        lock.mkdir()
        (lock / "pid").write_text("896")
        result = inv.inventory(self.repo, self.proc)
        self.assertIn("ORPHAN_ARCHIVE_WATCHER_REQUIRES_COORDINATION", result["reasons"])
        self.assertIn("BOOT_MAINTENANCE_HANDSHAKE_NOT_IMPLEMENTED", result["reasons"])
        self.assertEqual(len(result["processes"]), 6)
        self.assertEqual(inv.read_process(self.proc, 896)["start_ticks"], 12345)
        self.assertFalse(result["installation_completed"])

    def test_unrelated_diagnostic_process_not_mistaken_for_boot(self):
        self.process(700, 1, "grep TCG_AUTO_START.sh")
        result = inv.inventory(self.repo, self.proc)
        self.assertEqual(result["processes"], [])
        self.assertNotIn("BOOT_MAINTENANCE_HANDSHAKE_NOT_IMPLEMENTED", result["reasons"])

    def test_duplicate_launcher_is_ambiguous(self):
        self.process(896, 1, "bash execution/start_tablet_unified_v897.sh")
        self.process(897, 1, "bash execution/start_tablet_unified_v897.sh")
        result = inv.inventory(self.repo, self.proc)
        self.assertIn("REQUIRED_ROLES_NOT_UNIQUELY_VERIFIED", result["reasons"])
        self.assertIn("SUPERVISOR_OR_LAUNCHER_AMBIGUOUS", result["reasons"])

    def test_bad_lock_symlink_hold(self):
        (self.repo / ".tcg_android_start.lock").mkdir()
        (self.repo / ".tcg_android_start.lock" / "pid").symlink_to(self.root / "secret")
        result = inv.inventory(self.repo, self.proc)
        self.assertIn("UNSAFE_LOCK_SYMLINK", result["reasons"])

    def test_disappearing_proc_does_not_crash(self):
        self.process(1366, 1, "python -m execution.tablet_unified_runtime_v889")
        (self.proc / "1366" / "stat").unlink()
        self.assertIsNone(inv.read_process(self.proc, 1366))


if __name__ == "__main__":
    unittest.main()

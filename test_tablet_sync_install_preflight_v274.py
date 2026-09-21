#!/usr/bin/env python3
from pathlib import Path
import unittest


class TabletSyncInstallPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = Path("TABLET_GDRIVE_SYNC_INSTALL.sh").read_text(encoding="utf-8")

    def test_installer_requires_full_runtime_dependency_chain(self):
        for name in (
            "TABLET_GDRIVE_SYNC.sh",
            "tablet_gdrive_sync.py",
            "tablet_gdrive_sync_hardening.py",
            "tablet_gdrive_sync_hardening_contextual.py",
            "tablet_gdrive_sync_perf_v262.py",
        ):
            self.assertIn(name, self.src)

    def test_installer_compiles_contextual_and_perf_layers(self):
        compile_block = self.src.split("python -m py_compile", 1)[1].split("bash -n", 1)[0]
        self.assertIn("tablet_gdrive_sync.py", compile_block)
        self.assertIn("tablet_gdrive_sync_hardening.py", compile_block)
        self.assertIn("tablet_gdrive_sync_hardening_contextual.py", compile_block)
        self.assertIn("tablet_gdrive_sync_perf_v262.py", compile_block)

    def test_installer_preflights_required_drive_folders(self):
        self.assertIn("for subdir in to_tablet receipts", self.src)
        self.assertIn('${REMOTE}:${REMOTE_ROOT}/${subdir}', self.src)

    def test_installer_verifies_crond_really_started(self):
        self.assertIn('if ! pgrep -x crond >/dev/null 2>&1; then', self.src)
        self.assertIn("자동 동기화를 보장할 수 없습니다", self.src)

    def test_schedule_documentation_matches_producer_and_tablet_slots(self):
        self.assertIn("07:00 / 19:00 KST", self.src)
        self.assertIn('CRON_LINE="0 8,20 * * *', self.src)
        self.assertIn("주기: 12시간마다 1회", self.src)


if __name__ == "__main__":
    unittest.main()

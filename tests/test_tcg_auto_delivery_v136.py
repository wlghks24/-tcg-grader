#!/usr/bin/env python3
"""Drive/GitHub delivery diagnostic: fail-closed black-box regression."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts/TCG_TABLET_AUTO_DELIVERY_CHECK.sh"
REQUIRED = ("TABLET_GDRIVE_SYNC_INSTALL.sh", "TABLET_GDRIVE_SYNC.sh",
            "tablet_gdrive_sync.py", "tablet_gdrive_sync_hardening.py",
            "tablet_gdrive_sync_hardening_contextual.py",
            "tablet_gdrive_sync_perf_v262.py")


class DeliveryDoctorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.repo = self.home / "repo"
        (self.repo / "scripts").mkdir(parents=True)
        shutil.copy(SOURCE, self.repo / "scripts/TCG_TABLET_AUTO_DELIVERY_CHECK.sh")
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.log = self.home / "calls.log"
        for name in REQUIRED:
            (self.repo / name).write_text('#!/bin/bash\necho ' + name + ' >> "$TCG_TEST_LOG"\n')
        (self.repo / "TABLET_SCHEDULED_UPDATE.sh").write_text(
            '#!/bin/bash\necho GITHUB:"$1" >> "$TCG_TEST_LOG"\n')
        for name, body in {
            "rclone": '''#!/bin/bash
case "$1" in
  listremotes) [ "${REMOTE_READY:-yes}" = yes ] && echo gdrive: ;;
  lsf) [ "${FOLDERS_READY:-yes}" = yes ] || exit 1
    case "$2" in
      */receipts) echo "${RECEIPT_NAME:-TABLET_SYNC_RECEIPT_gpt-20260920T102500Z-21dfae76bf8c.json}" ;;
      */to_tablet) echo "${MANIFEST_NAME:-manifest_20261003T100521Z_gpt-20261003T100521Z-92a8691a7e46.json}" ;;
    esac ;;
esac
''',
            "crontab": '#!/bin/bash\necho "0 8,20 * * * TABLET_GDRIVE_SYNC.sh"\n',
            "pgrep": '#!/bin/bash\nexit 0\n',
            "git": '#!/bin/bash\necho a7f9c6e2e147\n',
        }.items():
            p = self.bin / name
            p.write_text(body)
            p.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home),
                        TCG_TEST_LOG=str(self.log),
                        PATH=str(self.bin) + ':' + os.environ.get('PATH', ''))

    def run_script(self, mode, **env):
        return subprocess.run(
            ['bash', str(self.repo / "scripts/TCG_TABLET_AUTO_DELIVERY_CHECK.sh"), mode],
            capture_output=True, text=True, timeout=8, env={**self.env, **env})

    def written(self):
        return self.log.read_text() if self.log.exists() else ''

    def test_read_only_status_never_claims_delivery(self):
        p = self.run_script("status")
        self.assertEqual(0, p.returncode, p.stderr)
        self.assertIn("END_TO_END_DELIVERY=HOLD", p.stdout)
        self.assertIn("GPT_PUBLISHER=not-verified", p.stdout)
        self.assertNotIn("install", self.written())

    def test_old_receipt_does_not_prove_new_package(self):
        p = self.run_script("status")
        self.assertEqual(0, p.returncode, p.stderr)
        self.assertIn("RECEIPTS=present-not-content-verified", p.stdout)
        self.assertIn("LATEST_PACKAGE_RECEIPT=missing", p.stdout)
        self.assertIn("DELIVERY_GAP=latest-package-without-receipt", p.stdout)
        self.assertIn("END_TO_END_DELIVERY=HOLD", p.stdout)
        self.assertEqual("", self.written())

    def test_matching_receipt_is_only_unverified_evidence(self):
        p = self.run_script(
            "status",
            RECEIPT_NAME="TABLET_SYNC_RECEIPT_gpt-20261003T100521Z-92a8691a7e46.json",
        )
        self.assertEqual(0, p.returncode, p.stderr)
        self.assertIn("LATEST_PACKAGE_RECEIPT=present-not-content-verified", p.stdout)
        self.assertNotIn("DELIVERY_GAP=latest-package-without-receipt", p.stdout)
        self.assertIn("END_TO_END_DELIVERY=HOLD", p.stdout)

    def test_invalid_manifest_cannot_be_matched(self):
        p = self.run_script("status", MANIFEST_NAME="manifest_fake.json")
        self.assertEqual(0, p.returncode, p.stderr)
        self.assertIn("NEWEST_MANIFEST_FILENAME=none", p.stdout)
        self.assertIn("LATEST_PACKAGE_RECEIPT=no-package-to-check", p.stdout)
        self.assertIn("END_TO_END_DELIVERY=HOLD", p.stdout)

    def test_missing_auth_no_partial_install(self):
        p = self.run_script("install", REMOTE_READY="no")
        self.assertEqual(11, p.returncode)
        self.assertEqual('', self.written())

    def test_no_remote_folder_no_partial_install(self):
        p = self.run_script("install", FOLDERS_READY="no")
        self.assertEqual(12, p.returncode)
        self.assertEqual('', self.written())

    def test_block_unsafe_remote_and_missing_runtime(self):
        p = self.run_script("install", TCG_GDRIVE_ROOT="../unsafe")
        self.assertEqual(10, p.returncode)
        self.assertEqual('', self.written())
        (self.repo / "tablet_gdrive_sync_perf_v262.py").unlink()
        self.assertEqual(13, self.run_script("install").returncode)
        self.assertEqual('', self.written())

    def test_drive_only_does_not_touch_github(self):
        p = self.run_script("install-drive")
        self.assertEqual(0, p.returncode, p.stderr)
        self.assertIn("TABLET_GDRIVE_SYNC_INSTALL.sh", self.written())
        self.assertNotIn("GITHUB:install", self.written())

    def test_both_installs_after_preflight(self):
        p = self.run_script("install")
        self.assertEqual(0, p.returncode, p.stderr)
        calls = self.written()
        self.assertLess(calls.index("GITHUB:install"), calls.index("TABLET_GDRIVE_SYNC_INSTALL.sh"))

    def test_run_now_uses_validated_receiver(self):
        p = self.run_script("run-now")
        self.assertEqual(0, p.returncode, p.stderr)
        self.assertIn("TABLET_GDRIVE_SYNC.sh", self.written())
        self.assertNotIn("GITHUB:install", self.written())


if __name__ == "__main__":
    unittest.main(verbosity=2)

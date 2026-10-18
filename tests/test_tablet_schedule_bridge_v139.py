#!/usr/bin/env python3
"""Regression gate for GPT -> Drive -> KST tablet handoff."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TabletDeliveryBridgeTests(unittest.TestCase):
    def test_producer_is_0700_and_1900_kst(self):
        workflow = (ROOT / ".github/workflows/gpt-tcg-drive-package.yml").read_text(encoding="utf-8")
        self.assertIn("cron: '0 10,22 * * *'", workflow)
        self.assertEqual(sorted((utc + 9) % 24 for utc in (10, 22)), [7, 19])

    def test_receiver_is_one_hour_after_producer(self):
        installer = (ROOT / "TABLET_GDRIVE_SYNC_INSTALL.sh").read_text(encoding="utf-8")
        self.assertIn('CRON_LINE="0 8,20 * * *', installer)
        self.assertEqual([(kst + 1) % 24 for kst in (7, 19)], [8, 20])

    def test_installer_rejects_wrong_timezone(self):
        installer = (ROOT / "TABLET_GDRIVE_SYNC_INSTALL.sh").read_text(encoding="utf-8")
        self.assertIn('if [ "$(date +%z)" != "+0900" ]; then', installer)
        self.assertIn("exit 7", installer)

    def test_one_entrypoint_for_device_status_install_and_run(self):
        main = (ROOT / "main").read_text(encoding="utf-8")
        for action in ("status", "install", "run-now"):
            self.assertIn("exec bash scripts/TCG_TABLET_AUTO_DELIVERY_CHECK.sh " + action, main)
        for action in ("sync-status", "sync-install", "sync-now"):
            self.assertIn(action, main)


if __name__ == "__main__":
    unittest.main()

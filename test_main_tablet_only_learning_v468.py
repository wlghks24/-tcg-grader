#!/usr/bin/env python3
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


class TabletOnlyLearningMainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = (ROOT / "main").read_text(encoding="utf-8")
        cls.schedule = (ROOT / "TABLET_SCHEDULED_UPDATE.sh").read_text(encoding="utf-8")

    def test_tablet_learning_command_uses_existing_verified_v400_path(self):
        self.assertIn("tablet-learn|learn)", self.main)
        self.assertIn(
            "python tablet_autonomous_evolution_v400.py --domain tablet_gpt "
            "--execute-safe-learning --apply-capabilities --train-meta --apply-skills --quiet",
            self.main,
        )
        self.assertIn("verified_collection_neural as query_neural", self.main)
        self.assertIn("verified_collection_job_neural as job_neural", self.main)

    def test_learning_status_is_local_and_colab_drive_are_not_required(self):
        self.assertIn("learn-status)", self.main)
        self.assertIn('"mode": "tablet-only"', self.main)
        self.assertIn('"colab_required": False', self.main)
        self.assertIn('"drive_required": False', self.main)
        self.assertNotIn("google.colab", self.main)
        self.assertNotIn("drive.mount(", self.main)

    def test_local_only_command_removes_only_legacy_drive_automation(self):
        self.assertIn("local-only|cloud-off)", self.main)
        self.assertIn('grep -Fv "TABLET_GDRIVE_SYNC.sh"', self.main)
        self.assertIn('"$HOME/.termux/boot/00_TCG_GDRIVE_RECOVERY.sh"', self.main)
        self.assertIn('"$HOME/.termux/boot/TCG_GDRIVE_SYNC_BOOT.sh"', self.main)
        self.assertIn("Drive 파일과 rclone 계정/설정은 삭제하지 않았습니다.", self.main)
        block = self.main[
            self.main.index("  local-only|cloud-off)") :
            self.main.index("  recover)", self.main.index("  local-only|cloud-off)"))
        ]
        self.assertNotRegex(block, r"(?m)^\\s*rclone\\b")
        self.assertNotIn("deletefile", block)
        self.assertNotIn("pkill", block)
        self.assertNotRegex(block, r"(?m)^\\s*kill\\b")

    def test_daily_scheduler_already_runs_same_local_safe_learning_stack(self):
        self.assertIn(
            "python tablet_autonomous_evolution_v400.py --domain tablet_gpt "
            "--execute-safe-learning --apply-capabilities --train-meta --apply-skills",
            self.schedule,
        )
        self.assertIn("run_autonomy_cycle", self.schedule)


if __name__ == "__main__":
    unittest.main()

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

    def test_daily_scheduler_already_runs_same_local_safe_learning_stack(self):
        self.assertIn(
            "python tablet_autonomous_evolution_v400.py --domain tablet_gpt "
            "--execute-safe-learning --apply-capabilities --train-meta --apply-skills",
            self.schedule,
        )
        self.assertIn("run_autonomy_cycle", self.schedule)


if __name__ == "__main__":
    unittest.main()

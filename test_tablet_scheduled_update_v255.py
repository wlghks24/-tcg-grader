from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


class TabletScheduledUpdateV255Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = (ROOT / 'TABLET_SCHEDULED_UPDATE.sh').read_text(encoding='utf-8')
        cls.main = (ROOT / 'main').read_text(encoding='utf-8')

    def test_main_exposes_update_management(self):
        for token in ('update-install', 'update-now', 'update-status', 'update-remove'):
            self.assertIn(token, self.main)
        self.assertIn('TABLET_SCHEDULED_UPDATE.sh', self.main)

    def test_schedule_reuses_existing_fail_closed_updater(self):
        self.assertIn('bash "$ROOT/ANDROID_UPDATE_AND_START.sh"', self.script)
        self.assertIn('git fetch --prune origin main', self.script)
        self.assertIn('sha origin/main', self.script)
        self.assertIn('if [ "$before" = "$remote" ]', self.script)
        self.assertIn('if [ "$rc" -eq 0 ] && [ "$after" = "$remote" ]', self.script)

    def test_schedule_does_not_mutate_github_or_force_local_state(self):
        forbidden = ('git push', 'reset --hard', 'git checkout -f', 'git clean -f', 'gh pr', 'curl ', 'wget ')
        for token in forbidden:
            self.assertNotIn(token, self.script)

    def test_schedule_is_bounded_and_boot_supervised(self):
        self.assertIn('TCG_UPDATE_INTERVAL_HOURS:-24', self.script)
        self.assertIn('INTERVAL_HOURS" -lt 1', self.script)
        self.assertIn('INTERVAL_HOURS" -gt 168', self.script)
        self.assertIn('sleep 30', self.script)
        self.assertIn('sleep "\\$((INTERVAL*3600))"', self.script)
        self.assertIn('Termux:Boot', self.script)

    def test_status_and_lock_are_persistent(self):
        self.assertIn('.local/state/tcg-grader/scheduled-update', self.script)
        self.assertIn('STATUS_FILE=', self.script)
        self.assertIn('LOCK_DIR=', self.script)
        self.assertIn('FETCH_FAILED', self.script)
        self.assertIn('UP_TO_DATE', self.script)
        self.assertIn('UPDATED', self.script)
        self.assertIn('UPDATE_FAILED', self.script)


if __name__ == '__main__':
    unittest.main()

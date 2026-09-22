from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


class TabletScheduledUpdateV256Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script = (ROOT / 'TABLET_SCHEDULED_UPDATE.sh').read_text(encoding='utf-8')
        cls.main = (ROOT / 'main').read_text(encoding='utf-8')
        cls.updater = (ROOT / 'ANDROID_UPDATE_AND_START.sh').read_text(encoding='utf-8')
        cls.recover = (ROOT / 'ANDROID_RECOVER_UPDATE.sh').read_text(encoding='utf-8')
        cls.manifest = (ROOT / 'tablet_runtime_manifest.py').read_text(encoding='utf-8')
        cls.final_verify = (ROOT / 'VERIFY_TABLET_FINAL.sh').read_text(encoding='utf-8')

    def test_main_exposes_update_management(self):
        for token in ('update-install', 'update-now', 'update-status', 'update-remove'):
            self.assertIn(token, self.main)
        self.assertIn('TABLET_SCHEDULED_UPDATE.sh', self.main)

    def test_main_auto_prepares_scheduler_before_server_start(self):
        ensure = 'bash TABLET_SCHEDULED_UPDATE.sh ensure'
        server = 'exec bash ANDROID_UPDATE_AND_START.sh'
        self.assertIn(ensure, self.main)
        self.assertIn(server, self.main)
        self.assertLess(self.main.index(ensure), self.main.index(server))
        self.assertIn('부팅 후 자동 main 확인 준비가 완전하지 않습니다', self.main)

    def test_schedule_uses_canonical_main_and_update_only_path(self):
        canonical = 'git fetch "$OFFICIAL_HTTPS" refs/heads/main:refs/remotes/origin/main'
        self.assertIn('OFFICIAL_HTTPS="https://github.com/wlghks24/-tcg-grader.git"', self.script)
        self.assertIn(canonical, self.script)
        self.assertIn(canonical, self.updater)
        self.assertIn(canonical, self.recover)
        for source in (self.script, self.updater, self.recover):
            self.assertNotIn('git fetch --prune "$OFFICIAL_HTTPS"', source)
        self.assertIn('TCG_UPDATE_ONLY=1 bash "$ROOT/ANDROID_UPDATE_AND_START.sh"', self.script)
        self.assertIn('remote_after="$(sha origin/main)"', self.script)

    def test_update_only_mode_returns_before_server_exec(self):
        mode = 'if [ "${TCG_UPDATE_ONLY:-0}" = "1" ]; then'
        server = 'exec bash START_TCG_UPDATER_ANDROID.sh'
        self.assertIn(mode, self.updater)
        self.assertIn(server, self.updater)
        self.assertLess(self.updater.index(mode), self.updater.index(server))
        self.assertIn('exit 0', self.updater[self.updater.index(mode):self.updater.index(server)])

    def test_postcheck_mismatch_is_not_false_success(self):
        self.assertIn('POSTCHECK_MISMATCH', self.script)
        self.assertIn('if [ "$rc" -eq 0 ]; then', self.script)
        self.assertIn('return 4', self.script)
        self.assertIn('if [ "$rc" -eq 0 ] && [ "$after" = "$remote_after" ]; then', self.script)

    def test_schedule_does_not_mutate_github_or_force_local_state(self):
        forbidden = ('git push', 'reset --hard', 'git checkout -f', 'git clean -f', 'gh pr', 'curl ', 'wget ')
        for token in forbidden:
            self.assertNotIn(token, self.script)

    def test_schedule_is_bounded_boot_supervised_and_recovers_stale_lock(self):
        self.assertIn('TCG_UPDATE_INTERVAL_HOURS:-24', self.script)
        self.assertIn('INTERVAL_HOURS" -lt 1', self.script)
        self.assertIn('INTERVAL_HOURS" -gt 168', self.script)
        self.assertIn('sleep 30', self.script)
        self.assertIn('sleep "$((INTERVAL_HOURS*3600))"', self.script)
        self.assertIn('kill -0 "$owner"', self.script)

    def test_scheduler_self_heals_and_reports_termux_boot_readiness(self):
        for token in ('ensure_schedule()', 'boot_loop()', 'write_boot_heartbeat()', 'termux_boot_state()'):
            self.assertIn(token, self.script)
        self.assertIn('com.termux.boot', self.script)
        self.assertIn('TERMUX_BOOT=$boot_state', self.script)
        self.assertIn('BOOT_LOOP_HEARTBEAT=not-seen', self.script)
        self.assertIn('TABLET_SCHEDULED_UPDATE.sh" boot-loop', self.script)
        self.assertIn('예약 업데이트 부팅 스크립트가 없거나 구형이라 자동 복구합니다', self.script)

    def test_runtime_delivery_fails_closed_if_scheduler_is_missing(self):
        self.assertIn('"TABLET_SCHEDULED_UPDATE.sh"', self.manifest)
        self.assertIn('TABLET_SCHEDULED_UPDATE.sh', self.final_verify)
        self.assertIn('bash -n TABLET_SCHEDULED_UPDATE.sh', self.final_verify)


if __name__ == '__main__':
    unittest.main()

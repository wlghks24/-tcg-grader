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

    def test_update_now_rechecks_scheduler_after_updating_code(self):
        case = self.main[self.main.index('  update-now)'):self.main.index('  update-status)')]
        self.assertIn('bash TABLET_SCHEDULED_UPDATE.sh run', case)
        self.assertIn('bash TABLET_SCHEDULED_UPDATE.sh ensure || true', case)
        self.assertNotIn('exec bash TABLET_SCHEDULED_UPDATE.sh run', case)

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


    def test_update_only_mode_holds_when_target_not_reached(self):
        mode = 'if [ "${TCG_UPDATE_ONLY:-0}" = "1" ]; then'
        block = self.updater[self.updater.index(mode):self.updater.index('exec bash START_TCG_UPDATER_ANDROID.sh')]
        self.assertIn('final_update_head="$(git rev-parse HEAD', block)
        self.assertIn('expected_update_head="$(git rev-parse origin/main', block)
        self.assertIn('[HOLD] Android 안전 업데이트가 목표 main에 도달하지 못했습니다.', block)
        self.assertIn('exit 3', block)

    def test_verified_registry_is_preserved_as_runtime_state(self):
        runtime_start = self.updater.index('is_runtime_path() {')
        runtime_end = self.updater.index('\n}\n\nappend_line()', runtime_start)
        runtime_contract = self.updater[runtime_start:runtime_end]
        self.assertIn('tcg_game_registry.json', runtime_contract)
        self.assertIn('backup_and_normalize_runtime', self.updater)
        self.assertIn('restore_runtime_snapshot', self.updater)

    def test_postcheck_mismatch_is_not_false_success(self):
        self.assertIn('POSTCHECK_MISMATCH', self.script)
        self.assertIn('if [ "$rc" -eq 0 ]; then', self.script)
        self.assertIn('return 4', self.script)
        self.assertIn('if [ "$rc" -eq 0 ] && [ "$after" = "$remote_after" ]; then', self.script)

    def test_schedule_does_not_mutate_github_or_force_local_state(self):
        forbidden = ('git push', 'reset --hard', 'git checkout -f', 'git clean -f', 'gh pr', 'curl ', 'wget ')
        for token in forbidden:
            self.assertNotIn(token, self.script)

    def test_schedule_runs_once_daily_at_2300_kst(self):
        self.assertIn('SCHEDULE_HOUR="23"', self.script)
        self.assertIn('SCHEDULE_MINUTE="00"', self.script)
        self.assertIn('timezone(timedelta(hours=9))', self.script)
        self.assertIn('seconds_until_next_run()', self.script)
        self.assertIn('sleep "$wait_seconds"', self.script)
        self.assertIn('UPDATE_SCHEDULE=DAILY_${SCHEDULE_HOUR}:${SCHEDULE_MINUTE}_KST', self.script)
        self.assertIn('NEXT_RUN_KST=', self.script)
        self.assertNotIn('TCG_UPDATE_INTERVAL_HOURS', self.script)
        self.assertNotIn('INTERVAL_HOURS', self.script)
        self.assertNotIn('sleep "$((INTERVAL_HOURS*3600))"', self.script)
        self.assertIn('매일 23:00 KST 기능 업데이트 확인', self.main)

    def test_scheduler_self_heals_starts_now_and_reports_termux_boot_readiness(self):
        for token in (
            'ensure_schedule()', 'boot_loop()', 'write_boot_heartbeat()',
            'termux_boot_state()', 'start_loop_if_needed()',
        ):
            self.assertIn(token, self.script)
        self.assertIn('com.termux.boot', self.script)
        self.assertIn('TERMUX_BOOT=$boot_state', self.script)
        self.assertIn('BOOT_LOOP_HEARTBEAT=not-seen', self.script)
        self.assertIn('BOOT_LOOP_PID_FILE=', self.script)
        self.assertIn('BOOT_LOOP=$loop_state', self.script)
        self.assertIn('nohup bash "$ROOT/TABLET_SCHEDULED_UPDATE.sh" boot-loop', self.script)
        self.assertIn('TABLET_SCHEDULED_UPDATE.sh" boot-loop', self.script)
        self.assertIn('예약 업데이트 부팅 스크립트가 없거나 구형이라 자동 복구합니다', self.script)
        self.assertIn('start_loop_if_needed', self.script[self.script.index('install_schedule()'):self.script.index('ensure_schedule()')])
        self.assertIn('start_loop_if_needed', self.script[self.script.index('ensure_schedule()'):self.script.index('boot_loop()')])

    def test_scheduler_validates_pid_identity_before_trusting_or_killing(self):
        for token in (
            'pid_cmdline()', 'pid_matches_mode()', 'pid_matches_update()',
            'stop_verified_loop_process()', '기록된 PID가 예약 루프가 아니므로 종료하지 않고',
            '기록된 PID가 예약 루프가 아니므로 종료 신호를 보내지 않습니다',
        ):
            self.assertIn(token, self.script)
        self.assertIn('[[ "$cmdline" == *"TABLET_SCHEDULED_UPDATE.sh"* ]]', self.script)
        self.assertIn('if ! pid_matches_mode "$owner" "boot-loop"; then', self.script)
        self.assertNotIn('if [ -n "$owner" ] && kill -0 "$owner" 2>/dev/null; then', self.script)

    def test_scheduler_versions_pid_state_and_migrates_legacy_loop(self):
        for token in (
            'SCHEDULER_VERSION="daily-2300-kst-v2"',
            'read_boot_loop_pid()', 'read_boot_loop_version()', 'write_boot_loop_identity()',
            'VERSION=$SCHEDULER_VERSION', 'BOOT_LOOP_VERSION=$SCHEDULER_VERSION',
            'stale-version:$owner:$owner_version',
            '구형 예약 루프를 현재 23:00 KST 스케줄로 교체합니다',
        ):
            self.assertIn(token, self.script)
        self.assertIn("printf 'legacy'", self.script)
        self.assertIn('[ "$owner_version" = "$SCHEDULER_VERSION" ]', self.script)

    def test_each_run_reconciles_scheduler_so_old_hourly_parent_can_self_migrate(self):
        self.assertIn('run_and_reconcile_schedule()', self.script)
        body = self.script[self.script.index('run_and_reconcile_schedule()'):self.script.index('case "${1:-status}"')]
        self.assertIn('run_update || rc=$?', body)
        self.assertIn('run_autonomy_cycle || autonomy_rc=$?', body)
        self.assertIn('ensure_schedule || true', body)
        self.assertLess(body.index('run_update || rc=$?'), body.index('run_autonomy_cycle || autonomy_rc=$?'))
        self.assertLess(body.index('run_autonomy_cycle || autonomy_rc=$?'), body.index('ensure_schedule || true'))
        self.assertIn('run|now) run_and_reconcile_schedule', self.script)

    def test_daily_scheduler_runs_bounded_verified_autonomy_cycle(self):
        for token in (
            'run_autonomy_cycle()',
            'AUTONOMY_STATUS_FILE="${STATE_DIR}/autonomy-status.env"',
            'python "$ROOT/tablet_runtime_manifest.py" --check --compile',
            'python "$ROOT/tablet_autonomous_evolution_v400.py" --self-test',
            'python tablet_autonomous_evolution_v400.py --domain tablet_gpt --execute-safe-learning --apply-capabilities --train-meta --apply-skills',
            'PRECHECK_FAILED',
            'SELFTEST_FAILED',
            'fail-closed로 기존 정책/모델 유지',
            'AUTONOMY_STATUS=not-run',
        ):
            self.assertIn(token, self.script)
        self.assertNotIn('git push', self.script)
        self.assertNotIn('source_code_auto_rewrite', self.script)
        self.assertIn('tmp="${AUTONOMY_STATUS_FILE}.tmp.$$"', self.script)
        self.assertNotIn('tmp="${AUTONOMY_STATUS_FILE}.tmp.$"\n', self.script)

    def test_runtime_delivery_fails_closed_if_scheduler_is_missing(self):
        self.assertIn('"TABLET_SCHEDULED_UPDATE.sh"', self.manifest)
        self.assertIn('TABLET_SCHEDULED_UPDATE.sh', self.final_verify)
        self.assertIn('bash -n TABLET_SCHEDULED_UPDATE.sh', self.final_verify)

    def test_v407_neural_navigation_does_not_expand_scheduler_authority(self):
        # V407 is a bounded presentation-policy change. The daily scheduler may
        # invoke the existing verified autonomy entrypoint, but it must not
        # directly manipulate UI source files or navigation policy.
        self.assertNotIn('feature_category_nav.js', self.script)
        self.assertNotIn('tablet_autonomy_dashboard_v400.js', self.script)
        self.assertNotIn('applyAdaptiveDock', self.script)


if __name__ == '__main__':
    unittest.main()

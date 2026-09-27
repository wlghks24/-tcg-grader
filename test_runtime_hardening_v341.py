from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


class RuntimeHardeningV341Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schedule = (ROOT / 'TABLET_SCHEDULED_UPDATE.sh').read_text(encoding='utf-8')
        cls.sw = (ROOT / 'sw.js').read_text(encoding='utf-8')
        cls.alignment = (ROOT / '.github/workflows/tablet-gpt-tcg-grader-main-alignment.yml').read_text(encoding='utf-8')

    def test_scheduler_identity_and_live_migration(self):
        for token in (
            'SCHEDULER_VERSION="daily-2300-kst-v2"',
            'pid_matches_mode()',
            'stop_verified_loop_process()',
            'read_boot_loop_version()',
            'run_and_reconcile_schedule()',
            'ensure_schedule || true',
            'stale-version:$owner:$owner_version',
        ):
            self.assertIn(token, self.schedule)
        self.assertIn('run|now) run_and_reconcile_schedule', self.schedule)
        self.assertIn("printf 'legacy'", self.schedule)

    def test_scheduler_does_not_kill_unrelated_pid(self):
        self.assertIn('if ! pid_matches_mode "$owner" "boot-loop"; then', self.schedule)
        self.assertIn('기록된 PID가 예약 루프가 아니므로 종료 신호를 보내지 않습니다', self.schedule)
        self.assertNotIn('if [ -n "$owner" ] && kill -0 "$owner" 2>/dev/null; then', self.schedule)

    def test_pwa_exact_fallback_precedes_query_agnostic_fallback(self):
        exact = 'const exact=await caches.match(request);'
        broad = 'const cached=await caches.match(request,{ignoreSearch:true});'
        self.assertIn(exact, self.sw)
        self.assertIn(broad, self.sw)
        self.assertLess(self.sw.index(exact), self.sw.index(broad))
        self.assertIn("const CACHE='tcg-v276-network-first-runtime'", self.sw)
        self.assertIn("fetch(event.request,{cache:'no-store'})", self.sw)

    def test_sync_generation_binding(self):
        for token in (
            "expected_delta = f'TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v{version}_delta.json'",
            "assert contract['delta_snapshot'] == expected_delta",
            "assert contract['receiver_receipt'] == expected_receipt",
            "assert contract['verification_test'] == expected_test",
            'int(prior_match.group(1)) < version',
        ):
            self.assertIn(token, self.alignment)


if __name__ == '__main__':
    unittest.main(verbosity=2)

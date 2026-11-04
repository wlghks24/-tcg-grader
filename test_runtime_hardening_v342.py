from pathlib import Path
import unittest
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent


class RuntimeHardeningV342Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schedule = (ROOT / 'TABLET_SCHEDULED_UPDATE.sh').read_text(encoding='utf-8')
        cls.sw = (ROOT / 'sw.js').read_text(encoding='utf-8')

    def test_scheduler_identity_and_live_migration(self):
        for token in (
            'SCHEDULER_VERSION="daily-2300-kst-v3"',
            'pid_matches_mode()',
            'stop_verified_loop_process()',
            'read_boot_loop_version()',
            'run_and_reconcile_schedule()',
            'ensure_schedule || true',
            'stale-version:$owner:$owner_version',
            'stale-heartbeat:$owner',
            'heartbeat_is_stale()',
            'kill -KILL "$owner"',
            "trap 'exit 0' INT TERM HUP",
        ):
            self.assertIn(token, self.schedule)
        self.assertIn('run|now) run_and_reconcile_schedule', self.schedule)
        self.assertIn("printf 'legacy'", self.schedule)

    def test_scheduler_does_not_kill_unrelated_pid(self):
        self.assertIn('if ! pid_matches_mode "$owner" "boot-loop"; then', self.schedule)
        self.assertIn('기록된 PID가 예약 루프가 아니므로 종료 신호를 보내지 않습니다', self.schedule)
        self.assertNotIn('if [ -n "$owner" ] && kill -0 "$owner" 2>/dev/null; then', self.schedule)

    def test_heartbeat_preserves_loop_start_and_tracks_current_heartbeat(self):
        self.assertIn('BOOT_LOOP_STARTED_AT=$started_at', self.schedule)
        self.assertIn('BOOT_LOOP_HEARTBEAT_AT=$(now)', self.schedule)
        self.assertIn('write_boot_heartbeat "$started_at"', self.schedule)

    def test_pwa_exact_fallback_precedes_query_agnostic_fallback(self):
        exact = 'const exact=await caches.match(request);'
        broad = 'const cached=await caches.match(request,{ignoreSearch:true});'
        self.assertIn(exact, self.sw)
        self.assertIn(broad, self.sw)
        self.assertLess(self.sw.index(exact), self.sw.index(broad))
        self.assertIn("const CACHE='tcg-v276-network-first-runtime'", self.sw)
        self.assertIn("fetch(event.request,{cache:'no-store'})", self.sw)


    def test_unified_navigation_never_replays_an_old_cache_instead_of_live_shell(self):
        # Run the real service-worker JS in a sandbox, not a grep-only test.
        if not shutil.which('node'):
            self.skipTest('Node runtime unavailable')
        script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const old=new Response('<html><body>OLD_LEGACY_SHELL</body></html>',{
  status:200,headers:{'Content-Type':'text/html; charset=utf-8'}});
const calls=[];
const sandbox={URL,Response,Headers,caches:{match:async(request,opts)=>{
  calls.push([String(request.url),opts?.ignoreSearch||false]);return old.clone();
}},self:{addEventListener:()=>{}}};
vm.runInNewContext(fs.readFileSync('sw.js','utf8'),sandbox);
(async()=>{
  const unified=['/tablet-unified','/tablet-events-all?game=naruto&region=JP',
    '/tablet-features','/index.html?feature=auto-grade',
    '/index.html?pane=home','/index.html?target=gradeStart',
    '/?pane=events'];
  for(const route of unified){
    const before=calls.length;
    const response=await sandbox.unavailableResponse({
      url:'http://127.0.0.1:8765'+route,mode:'navigate'});
    assert.equal(response.status,503,route);
    assert.ok(response.headers.get('content-type').includes('text/html'));
    assert.equal(response.headers.get('cache-control'),'no-store');
    const body=await response.text();
    assert.match(body,/최신 통합 화면 연결 확인 필요/);
    assert.match(body,/저장된 카드·원본 사진·수집 기록은 변경하지 않았습니다/);
    assert.doesNotMatch(body,/OLD_LEGACY_SHELL/);
    assert.equal(calls.length,before,'unified route must not access stale caches');
  }
  // Ordinary legacy routes retain the original exact-first offline fallback
  // and may still load their exact saved document.
  const regular=await sandbox.unavailableResponse({
    url:'http://127.0.0.1:8765/legacy-guide.html',mode:'navigate'});
  assert.equal(regular.status,200);
  assert.match(await regular.text(),/OLD_LEGACY_SHELL/);
  assert.ok(calls.length>0);
  const direct=await sandbox.unavailableResponse({
    url:'http://127.0.0.1:8765/index.html?pane=home',mode:'same-origin'});
  assert.equal(direct.status,200,'non-navigation static requests still use cache');
  assert.ok(calls.length>1);
})().catch(err=>{console.error(err);process.exit(1)});
"""
        run = subprocess.run(['node', '-e', script], cwd=ROOT, capture_output=True,
                             text=True, timeout=20)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)



if __name__ == '__main__':
    unittest.main(verbosity=2)

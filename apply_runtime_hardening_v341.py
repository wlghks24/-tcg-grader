from pathlib import Path
import re


def one(text, old, new, label):
    if text.count(old) != 1:
        raise SystemExit(f"{label}: expected one match, got {text.count(old)}")
    return text.replace(old, new, 1)


def function(text, name, replacement):
    pattern = re.compile(rf"(?ms)^{re.escape(name)}\(\) \{{\n.*?^\}}\n")
    text, count = pattern.subn(replacement.rstrip() + "\n", text, count=1)
    if count != 1:
        raise SystemExit(f"{name}: replacement count={count}")
    return text


p = Path("TABLET_SCHEDULED_UPDATE.sh")
s = p.read_text(encoding="utf-8")
s = one(s,
'''now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
sha() { git -C "$ROOT" rev-parse "$1" 2>/dev/null || printf 'unknown'; }

next_run_kst() {''',
'''now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
sha() { git -C "$ROOT" rev-parse "$1" 2>/dev/null || printf 'unknown'; }

pid_cmdline() {
  local pid="$1"
  case "$pid" in ''|*[!0-9]*) return 1 ;; esac
  [ -r "/proc/$pid/cmdline" ] || return 1
  tr '\\000' ' ' <"/proc/$pid/cmdline" 2>/dev/null
}

pid_matches_mode() {
  local pid="$1" mode="$2" cmdline=""
  case "$pid" in ''|*[!0-9]*) return 1 ;; esac
  kill -0 "$pid" 2>/dev/null || return 1
  cmdline="$(pid_cmdline "$pid")" || return 1
  [[ "$cmdline" == *"TABLET_SCHEDULED_UPDATE.sh"* ]] || return 1
  [[ " $cmdline " == *" $mode "* ]]
}

pid_matches_update() {
  pid_matches_mode "$1" "run" || pid_matches_mode "$1" "now"
}

next_run_kst() {''', "pid identity helpers")

s = function(s, "write_boot_heartbeat", r'''write_boot_heartbeat() {
  local started_at="${1:-unknown}" tmp
  tmp="${BOOT_HEARTBEAT_FILE}.tmp.$$"
  cat >"$tmp" <<EOF_HEARTBEAT
BOOT_LOOP_STARTED_AT=$started_at
BOOT_LOOP_HEARTBEAT_AT=$(now)
BOOT_LOOP_PID=$$
ROOT=$ROOT
UPDATE_SCHEDULE=DAILY_${SCHEDULE_HOUR}:${SCHEDULE_MINUTE}_KST
HEARTBEAT_NEXT_RUN_KST=$(next_run_kst)
EOF_HEARTBEAT
  mv "$tmp" "$BOOT_HEARTBEAT_FILE"
}''')

s = one(s,
'''  if [ -n "$owner" ] && kill -0 "$owner" 2>/dev/null; then
    echo "[안내] 예약 업데이트가 이미 실행 중입니다(PID $owner)."
    exit 0
  fi''',
'''  if [ -n "$owner" ] && pid_matches_update "$owner"; then
    echo "[안내] 예약 업데이트가 이미 실행 중입니다(PID $owner)."
    exit 0
  fi''', "update lock identity")

s = function(s, "start_loop_if_needed", r'''start_loop_if_needed() {
  local owner="" loop_log="${LOG_DIR}/boot-loop.log"
  if [ -r "$BOOT_LOOP_PID_FILE" ]; then owner="$(cat "$BOOT_LOOP_PID_FILE" 2>/dev/null || true)"; fi
  case "$owner" in ''|*[!0-9]*) owner="" ;; esac
  if [ -n "$owner" ] && pid_matches_mode "$owner" "boot-loop"; then
    echo "[OK] 예약 업데이트 루프 실행 중(PID $owner)"
    return 0
  fi
  if [ -n "$owner" ]; then echo "[안내] 오래되었거나 다른 프로세스가 재사용한 예약 PID를 폐기합니다: $owner"; fi
  rm -f "$BOOT_LOOP_PID_FILE" 2>/dev/null || true
  nohup bash "$ROOT/TABLET_SCHEDULED_UPDATE.sh" boot-loop >>"$loop_log" 2>&1 </dev/null &
  owner=$!
  sleep 1
  if pid_matches_mode "$owner" "boot-loop"; then
    echo "[OK] 예약 업데이트 루프 자동 시작(PID $owner)"
    return 0
  fi
  rm -f "$BOOT_LOOP_PID_FILE" 2>/dev/null || true
  echo "[오류] 예약 업데이트 루프 자동 시작 실패. 로그: $loop_log" >&2
  return 7
}''')

s = function(s, "boot_loop", r'''boot_loop() {
  local owner="" wait_seconds next_target started_at
  if [ -r "$BOOT_LOOP_PID_FILE" ]; then owner="$(cat "$BOOT_LOOP_PID_FILE" 2>/dev/null || true)"; fi
  case "$owner" in ''|*[!0-9]*) owner="" ;; esac
  if [ -n "$owner" ] && [ "$owner" != "$$" ] && pid_matches_mode "$owner" "boot-loop"; then
    echo "[안내] 예약 업데이트 루프가 이미 실행 중입니다(PID $owner)."
    return 0
  fi
  printf '%s\n' "$$" >"$BOOT_LOOP_PID_FILE"
  trap cleanup_boot_loop_pid EXIT INT TERM HUP
  started_at="$(now)"
  write_boot_heartbeat "$started_at"
  while true; do
    wait_seconds="$(seconds_until_next_run)" || { echo "[경고] 다음 23:00 KST 계산 실패; 60초 후 재시도" >&2; sleep 60; continue; }
    next_target="$(next_run_kst)" || next_target="unknown"
    echo "[$(now)] 다음 기능 업데이트 확인: ${next_target} (KST)"
    sleep "$wait_seconds" || true
    bash "$ROOT/TABLET_SCHEDULED_UPDATE.sh" run || true
    write_boot_heartbeat "$started_at"
  done
}''')

s = function(s, "remove_schedule", r'''remove_schedule() {
  local owner=""
  if [ -r "$BOOT_LOOP_PID_FILE" ]; then owner="$(cat "$BOOT_LOOP_PID_FILE" 2>/dev/null || true)"; fi
  case "$owner" in ''|*[!0-9]*) owner="" ;; esac
  if [ -n "$owner" ] && pid_matches_mode "$owner" "boot-loop"; then
    kill "$owner" 2>/dev/null || true
  elif [ -n "$owner" ]; then
    echo "[안내] 기록된 PID가 예약 루프가 아니므로 종료 신호를 보내지 않습니다: $owner"
  fi
  rm -f "$BOOT_LOOP_PID_FILE" "$BOOT_FILE"
  echo "[OK] 태블릿 예약 업데이트를 제거했습니다."
}''')

s = function(s, "show_status", r'''show_status() {
  local boot_state loop_state="not-running" owner=""
  boot_state="$(termux_boot_state)"
  if [ -r "$BOOT_LOOP_PID_FILE" ]; then owner="$(cat "$BOOT_LOOP_PID_FILE" 2>/dev/null || true)"; fi
  case "$owner" in ''|*[!0-9]*) owner="" ;; esac
  if [ -n "$owner" ] && pid_matches_mode "$owner" "boot-loop"; then loop_state="running:$owner"; elif [ -n "$owner" ]; then loop_state="stale-pid:$owner"; fi
  echo "현재 HEAD: $(sha HEAD)"
  if [ -f "$STATUS_FILE" ]; then cat "$STATUS_FILE"; else echo "예약 업데이트 실행 기록이 없습니다."; fi
  if [ -x "$BOOT_FILE" ] && grep -Fq 'TABLET_SCHEDULED_UPDATE.sh" boot-loop' "$BOOT_FILE" 2>/dev/null; then echo "SCHEDULE=installed"; else echo "SCHEDULE=not-installed"; fi
  echo "UPDATE_SCHEDULE=DAILY_${SCHEDULE_HOUR}:${SCHEDULE_MINUTE}_KST"
  echo "NEXT_RUN_KST=$(next_run_kst 2>/dev/null || echo unknown)"
  echo "BOOT_LOOP=$loop_state"
  echo "TERMUX_BOOT=$boot_state"
  if [ -f "$BOOT_HEARTBEAT_FILE" ]; then cat "$BOOT_HEARTBEAT_FILE"; else echo "BOOT_LOOP_HEARTBEAT=not-seen"; fi
}''')
p.write_text(s, encoding="utf-8")

p = Path("sw.js")
s = p.read_text(encoding="utf-8")
s = one(s, "// v324 refreshes tablet/PWA identity runtime while preserving the v276 cache ABI.", "// v341 refreshes tablet/PWA offline fallback while preserving the v276 cache ABI.", "sw generation note")
s = one(s,
"async function unavailableResponse(request){\n  const cached=await caches.match(request,{ignoreSearch:true});\n  if(cached)return request.mode==='navigate'?enhanceNavigationResponse(cached):cached;",
"async function unavailableResponse(request){\n  const exact=await caches.match(request);\n  if(exact)return request.mode==='navigate'?enhanceNavigationResponse(exact):exact;\n  const cached=await caches.match(request,{ignoreSearch:true});\n  if(cached)return request.mode==='navigate'?enhanceNavigationResponse(cached):cached;", "sw exact fallback")
p.write_text(s, encoding="utf-8")

p = Path(".github/workflows/tablet-gpt-tcg-grader-main-alignment.yml")
s = p.read_text(encoding="utf-8")
old = """          contract = json.loads(contract_path.read_text(encoding='utf-8'))
          delta_path = root / contract['delta_snapshot']
          receipt_path = root / contract['receiver_receipt']
          test_path = root / contract['verification_test']
"""
new = """          contract = json.loads(contract_path.read_text(encoding='utf-8'))
          expected_delta = f'TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v{version}_delta.json'
          expected_receipt = f'TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v{version}.json'
          expected_test = f'test_tablet_gpt_tcg_grader_sync_v{version}.py'
          assert contract['delta_snapshot'] == expected_delta
          assert contract['receiver_receipt'] == expected_receipt
          assert contract['verification_test'] == expected_test
          prior_match = contract_re.fullmatch(Path(contract['prior_contract']).name)
          assert prior_match and int(prior_match.group(1)) < version
          delta_path = root / contract['delta_snapshot']
          receipt_path = root / contract['receiver_receipt']
          test_path = root / contract['verification_test']
"""
s = one(s, old, new, "alignment generation binding")
p.write_text(s, encoding="utf-8")

Path("test_runtime_hardening_v341.py").write_text(r'''from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parent
class RuntimeHardeningV341Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schedule=(ROOT/"TABLET_SCHEDULED_UPDATE.sh").read_text(encoding="utf-8")
        cls.sw=(ROOT/"sw.js").read_text(encoding="utf-8")
        cls.css=(ROOT/"ui_tablet_refine_v122.css").read_text(encoding="utf-8")
        cls.alignment=(ROOT/".github/workflows/tablet-gpt-tcg-grader-main-alignment.yml").read_text(encoding="utf-8")
    def test_pid_identity(self):
        for token in ("pid_cmdline()","pid_matches_mode()","pid_matches_update()",'pid_matches_update "$owner"','stale-pid:$owner','종료 신호를 보내지 않습니다'): self.assertIn(token,self.schedule)
        self.assertGreaterEqual(self.schedule.count('pid_matches_mode "$owner" "boot-loop"'),4)
        self.assertNotIn('kill -0 "$owner"',self.schedule)
    def test_heartbeat(self):
        for token in ('BOOT_LOOP_STARTED_AT=$started_at','BOOT_LOOP_HEARTBEAT_AT=$(now)','HEARTBEAT_NEXT_RUN_KST=$(next_run_kst)','NEXT_RUN_KST=$(next_run_kst 2>/dev/null || echo unknown)'): self.assertIn(token,self.schedule)
    def test_pwa_exact_fallback(self):
        exact='const exact=await caches.match(request);'; broad='const cached=await caches.match(request,{ignoreSearch:true});'
        self.assertIn(exact,self.sw); self.assertIn(broad,self.sw); self.assertLess(self.sw.index(exact),self.sw.index(broad))
        self.assertIn("const CACHE='tcg-v276-network-first-runtime'",self.sw); self.assertIn("fetch(event.request,{cache:'no-store'})",self.sw)
        self.assertIn('@media(max-width:539px)',self.css)
    def test_sync_generation_binding(self):
        for token in ("expected_delta = f'TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v{version}_delta.json'","assert contract['delta_snapshot'] == expected_delta","assert contract['receiver_receipt'] == expected_receipt","assert contract['verification_test'] == expected_test",'int(prior_match.group(1)) < version'): self.assertIn(token,self.alignment)
if __name__ == "__main__": unittest.main(verbosity=2)
''',encoding="utf-8")

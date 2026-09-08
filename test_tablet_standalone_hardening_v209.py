from __future__ import annotations
from datetime import datetime,timedelta,timezone
from pathlib import Path
import tempfile,unittest
import collection_runtime_health as health
import tablet_runtime_manifest as manifest
import runtime_optimization_hardening as optimizer
ROOT=Path(__file__).resolve().parent
class TabletStandaloneHardeningV209(unittest.TestCase):
 def test_collection_health_recovery(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/"health.json"; health.mark_failure("auto",RuntimeError("https://example.com failed"),path=p)
   a=health.public_status(p); self.assertEqual(1,a["consecutive_failures"]); self.assertNotIn("https://",str(a["last_error"]))
   health.mark_success("recovery",path=p); b=health.public_status(p); self.assertTrue(b["healthy"]); self.assertEqual(0,b["consecutive_failures"])
 def test_stale(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/"health.json"; health.mark_success("seed",path=p)
   future=datetime.now(timezone.utc)+timedelta(seconds=health.STALE_AFTER_SECONDS+5)
   self.assertEqual("stale",health.public_status(p,now=future)["status"])
 def test_manifest(self):
  req={"tcg_updater.py","collection_runtime_health.py","update_releases.py","update_market_prices.py","update_promo_events.py",
       "graded_photo_multi_source.py","event_priority_watch.py","event_quick_watch.py","multi_route_event_discovery.py"}
  self.assertTrue(req.issubset(set(manifest.ACTIVE_RUNTIME_FILES)))
  r=manifest.audit(ROOT,compile_python=True); self.assertTrue(r["ok"],r); self.assertGreaterEqual(r["python_checked"],40)
 def test_auto_loop(self):
  src=(ROOT/"tcg_updater.py").read_text(encoding="utf-8"); loop=src[src.index("def auto_update_loop():"):src.index("\nclass Handler",src.index("def auto_update_loop():"))]
  self.assertNotIn("except Exception: pass",loop); self.assertIn("_retry_failed_automatic",loop); self.assertIn("AUTO_FAILURE_RETRY_SECONDS",src)
  self.assertIn("'report_ok':bool(report.get('ok_with_monitor', report.get('ok_with_aux', report.get('ok'))))",src)
  self.assertIn("'report_ok':bool(final_report.get('ok_with_monitor', final_report.get('ok_with_aux', final_report.get('ok'))))",src)
  self.assertIn("'collection_health':collection_health_status()",src)
 def test_v135_health(self):
  src=(ROOT/"tcg_updater_v135.py").read_text(encoding="utf-8"); self.assertIn("collection_health = core.collection_health_status()",src)
  self.assertIn("'collection_health': collection_health",src); self.assertIn("'ok': True",src)
 def test_candidate_before_merge(self):
  src=(ROOT/"ANDROID_UPDATE_AND_START.sh").read_text(encoding="utf-8")
  self.assertIn("verify_remote_candidate()",src); self.assertLess(src.index('verify_remote_candidate "$remote_head"'),src.index("git merge --ff-only origin/main"))
  self.assertIn("git worktree add --detach",src); self.assertIn("TCG_FINAL_SKIP_HEAD_MATCH=1",src)
 def test_manifest_wiring(self):
  launcher=(ROOT/"START_TCG_UPDATER_ANDROID.sh").read_text(encoding="utf-8")
  self.assertIn("tablet_runtime_manifest.py --check --compile",launcher)
  self.assertIn("tablet_runtime_manifest.py --check --compile",(ROOT/"VERIFY_TABLET_FINAL.sh").read_text(encoding="utf-8"))
  self.assertEqual(launcher,optimizer.patch_android_start(launcher))
 def test_current_user_verifier(self):
  for n in ("RUN_FULL_VERIFICATION.bat","전체프로그램검사.bat"):
   src=(ROOT/n).read_text(encoding="utf-8"); self.assertIn("verify_current_runtime.py",src); self.assertNotIn("run_repeated_verification.py",src)
if __name__=="__main__": unittest.main()

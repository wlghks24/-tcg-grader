"""V656: actual V374 report matching is not independent neural evidence."""
from __future__ import annotations
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from execution.tablet_autonomy_trial_provenance_v656 import TRIGGER, inspect

class V656ProofTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = datetime.now(timezone.utc)
        self.end = self.now - timedelta(minutes=3)
        self.start = self.end - timedelta(minutes=2)
        self.collector()
        self.trial()

    def collector(self):
        jobs=[]
        for name in ("market_prices.json", "market_watch.json"):
            p={"updated_at":self.end.isoformat(), "collection_status":"정상", "collection_errors":[]}
            p["entries" if name=="market_prices.json" else "items"] = {"mock":{"price":1}} if name=="market_prices.json" else []
            (self.root/name).write_text(json.dumps(p))
            jobs.append({"file":name,"ok":True,"updated_at":self.end.isoformat(),
                         "collection_errors":[],"remaining_collection_errors":[]})
        r={"trigger":TRIGGER,"started_at":self.start.isoformat(),"finished_at":self.end.isoformat(),
           "ok":True,"failure_count":0,"degraded_count":0,"fresh_failure_count":0,
           "results":jobs,"postflight_monitor":{"ok":True,"results":[
               {"file":x["file"],"ok":True} for x in jobs]}}
        (self.root/"auto_update_report.json").write_text(json.dumps(r))

    def trial(self, recipe="RECOVER_FRESHNESS"):
        t={"skill_id":"test-one","recipe":recipe,"gap_id":"market_freshness",
           "created_at":(self.end+timedelta(seconds=20)).isoformat(),
           "expires_at":(self.end+timedelta(seconds=20,hours=24)).isoformat(),
           "before":{"freshness":"hold","degraded_source_ratio":0.5,
                     "low_coverage_regions":["JP"]},
           "region":"JP","meta_features":[0.3]*10}
        s={"schema_version":4,"controller_version":"v374","updated_at":self.end.isoformat(),
           "active_skills":[],"suspended_recipes":[],"pending_trials":[t]}
        (self.root/"tablet_autonomy_skills_v374.json").write_text(json.dumps(s))

    def report(self):
        return json.loads((self.root/"auto_update_report.json").read_text())

    def set_report(self, r):
        (self.root/"auto_update_report.json").write_text(json.dumps(r))

    def test_matching_real_local_run_never_trains(self):
        original=sorted(x.name for x in self.root.iterdir())
        r=inspect(self.root, now=self.now)
        self.assertEqual("LOCAL_EXECUTION_CORRELATED_UNVERIFIED",r["status"])
        self.assertEqual("REFRESH_MARKET_DATA",r["trial"]["action_id"])
        self.assertEqual(0,r["verified_outcomes_created"])
        self.assertFalse(r["eligible_for_v373_training"])
        self.assertFalse(r["independent_external_attestation"])
        self.assertEqual(original, sorted(x.name for x in self.root.iterdir()))

    def test_missing_trial(self):
        (self.root/"tablet_autonomy_skills_v374.json").unlink()
        self.assertEqual("NO_PENDING_TRIAL",inspect(self.root,now=self.now)["reason"])

    def test_wrong_trigger(self):
        r=self.report();r["trigger"]="scheduled";self.set_report(r)
        self.assertEqual("NOT_EXECUTED_BY_V374",inspect(self.root,now=self.now)["reason"])

    def test_failed_postflight(self):
        r=self.report();r["postflight_monitor"]["ok"]=False;self.set_report(r)
        self.assertEqual("EVIDENCE_HOLD",inspect(self.root,now=self.now)["status"])

    def test_degraded_collector(self):
        r=self.report();r["degraded_count"]=1;self.set_report(r)
        self.assertEqual("EVIDENCE_HOLD",inspect(self.root,now=self.now)["status"])

    def test_tampered_output(self):
        (self.root/"market_prices.json").write_text('{"updated_at":"bad","collection_errors":[]}')
        self.assertEqual("EVIDENCE_HOLD",inspect(self.root,now=self.now)["status"])

    def test_observe_only_never_promoted(self):
        self.trial(recipe="OBSERVE_ONLY")
        self.assertEqual("NO_UNAMBIGUOUS_EXECUTED_TRIAL",inspect(self.root,now=self.now)["reason"])

    def test_corrupt_trial_is_preserved(self):
        f=self.root/"tablet_autonomy_skills_v374.json";f.write_text("not-json")
        self.assertEqual("SKILL_STATE_CORRUPT",inspect(self.root,now=self.now)["reason"])
        self.assertEqual("not-json",f.read_text())

    def test_symlink_never_followed(self):
        f=self.root/"tablet_autonomy_skills_v374.json";f.unlink();f.symlink_to(self.root/"none")
        self.assertEqual("SKILL_STATE_SYMLINK",inspect(self.root,now=self.now)["reason"])

    def test_stale_not_validated(self):
        self.end=self.now-timedelta(hours=50);self.start=self.end-timedelta(minutes=2)
        self.collector();self.trial()
        self.assertEqual("EVIDENCE_HOLD",inspect(self.root,now=self.now)["status"])

    def test_bad_trial_features(self):
        f=self.root/"tablet_autonomy_skills_v374.json";d=json.loads(f.read_text())
        d["pending_trials"][0]["meta_features"]=[0.3]*9;f.write_text(json.dumps(d))
        self.assertEqual("INVALID_META_FEATURES",inspect(self.root,now=self.now)["reason"])

    def test_existing_daily_scheduler_wired_without_new_timer(self):
        s=(Path(__file__).resolve().parents[1]/"TABLET_SCHEDULED_UPDATE.sh").read_text()
        self.assertIn("execution.tablet_autonomy_trial_provenance_v656",s)
        self.assertIn('SCHEDULE_HOUR="23"',s)
        self.assertNotIn("reset --hard",s)

if __name__=="__main__":
    unittest.main()

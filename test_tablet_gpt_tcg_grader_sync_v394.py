import hashlib
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent
CONTRACT=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V394.json"
DELTA=ROOT/"TCG_CROSSCHECK"/"TABLET_GPT"/"learning_snapshot_v394_delta.json"
RECEIPT=ROOT/"TCG_CROSSCHECK"/"TCG_GRADER"/"tablet_gpt_learning_receipt_v394.json"
BASE_SHA="62bc132373bc9dafb88d9057e8b3c54c2c388fea"
CANDIDATE_SHA="3b55feb3df6702a0996043429935b9570115d9e1"
LESSON_IDS=["TABLET-GPT-PWA-CACHE-ABI-COMPATIBILITY-V394","TABLET-GPT-CARD-RELEASE-SURFACE-V400"]

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def digest(value):
    raw=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

class TabletGptTcgGraderSyncV394Tests(unittest.TestCase):
    def test_generation_binding_digest_and_counts(self):
        c,d,r=load(CONTRACT),load(DELTA),load(RECEIPT)
        self.assertEqual(BASE_SHA,d["source_main_sha"])
        self.assertEqual(BASE_SHA,r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"],digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
        self.assertEqual(LESSON_IDS,r["accepted_lesson_ids"])
        self.assertEqual(86,c["prior_required_lesson_count"])
        self.assertEqual(2,c["delta_required_lesson_count"])
        self.assertEqual(88,c["current_required_lesson_count"])
        self.assertEqual("SYNCED_VERIFIED",r["status"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])

    def test_exact_candidate_covers_v400_release_and_cache_repairs(self):
        candidate=load(CONTRACT)["candidate_sync"]
        self.assertEqual(BASE_SHA,candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA,candidate["candidate_commit"])
        self.assertEqual(['VERIFY_TABLET_FINAL.sh','index.html','main','sw.js','tablet_autonomous_evolution_v398.py','tablet_autonomous_evolution_v399.py','tablet_autonomous_evolution_v400.py','tablet_autonomy_dashboard_v399.css','tablet_autonomy_dashboard_v399.js','tablet_autonomy_dashboard_v400.css','tablet_autonomy_dashboard_v400.js','tablet_runtime_manifest.py','tcg_updater.py'],candidate["watched_paths"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])

    def test_card_release_rules_are_fail_closed(self):
        c=load(CONTRACT)
        for key in (
            "card_release_surface_required",
            "card_release_verified_evidence_only_required",
            "card_release_missing_evidence_revalidation_required",
            "card_release_fact_invention_forbidden",
            "card_release_canonical_v373_steering_only_required",
            "card_release_exact_canary_rollback_required",
        ):
            self.assertTrue(c["rules"][key],key)
        r=load(RECEIPT)
        self.assertTrue(r["alignment_policy"]["card_release_surface_required"])
        self.assertTrue(r["alignment_policy"]["card_release_verified_evidence_only"])
        self.assertFalse(r["alignment_policy"]["card_release_fact_invention"])

    def test_service_worker_preserves_v276_cache_abi(self):
        sw=(ROOT/"sw.js").read_text(encoding="utf-8")
        self.assertIn("const CACHE='tcg-v276-network-first-runtime';",sw)
        self.assertNotIn("const CACHE='tcg-v277-network-first-runtime';",sw)

    def test_device_claims_remain_fail_closed(self):
        verification=load(RECEIPT)["verification"]
        self.assertTrue(verification["device_reverification_required"])
        self.assertFalse(verification["physical_tablet_runtime_verified"])
        self.assertFalse(verification["physical_drive_readback_verified"])

if __name__=="__main__":
    unittest.main()

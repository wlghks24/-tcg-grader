import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v330_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v331_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v331.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V331.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TabletGptTcgGraderSyncV331(unittest.TestCase):
    def test_verified_fx_lesson_and_source_lineage(self):
        prior, delta, receipt, contract = map(read, (PRIOR, DELTA, RECEIPT, CONTRACT))
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual(delta["schema_version"], receipt["schema_version"])
        self.assertEqual(delta["schema_version"], contract["schema_version"])
        self.assertEqual(delta["source_repository"], receipt["source_repository"])
        self.assertEqual(delta["source_main_sha"], receipt["source_main_sha"])
        self.assertEqual("6d9377077f02e2b8b7e0101bc5d1edd327b12f13", delta["source_main_sha"])
        self.assertEqual([{"pr": 282, "version": "v331", "merge_sha": delta["source_main_sha"]}], delta["covered_merges"])
        self.assertEqual(set(contract["current_required_merge_prs"]), set(read(ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT.json")["current_required_merge_prs"]) | {282})

    def test_lesson_digest_and_safe_receipt(self):
        delta, receipt, contract = map(read, (DELTA, RECEIPT, CONTRACT))
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        self.assertEqual(1, len(delta["lessons"]))
        lesson = delta["lessons"][0]
        self.assertEqual("TABLET-GPT-FX-LIVE-EXPIRY-V331", lesson["lesson_id"])
        self.assertEqual([lesson["lesson_id"]], receipt["accepted_lesson_ids"])
        self.assertEqual("passed", lesson["verification_result"])
        self.assertIs(lesson["regression_pass"], True)
        self.assertEqual("high", lesson["confidence_level"])
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertEqual(22, contract["current_required_lesson_count"])
        self.assertFalse(delta["share_policy"]["chatgpt_model_weights_exported"])
        self.assertFalse(delta["share_policy"]["raw_grading_calibration_shared"])
        self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])
        self.assertTrue(receipt["alignment_policy"]["blind_overwrite_forbidden"])
        self.assertTrue(receipt["alignment_policy"]["peer_verified_never_auto_promotes_local"])

    def test_live_fx_guard_and_freshness_watch(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        browser = (ROOT / "verify_browser_runtime.js").read_text(encoding="utf-8")
        contract = read(CONTRACT)
        self.assertIn('fxTimestamp=stamp;scheduleFxExpiry();result.ok=true;', html)
        self.assertIn('clearFxConversionDisplay();result.errors.push("환율자료")', html)
        self.assertIn('document.addEventListener("visibilitychange"', html)
        self.assertIn('window.addEventListener("focus"', html)
        self.assertIn("clearExpiredFx(expiry+1)", browser)
        watch = contract["freshness_watch"]
        self.assertIn("index.html", watch["exact_paths"])
        self.assertNotIn("index.html", watch["exclude_paths"])
        self.assertIn("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v331_delta.json", watch["exclude_paths"])
        self.assertTrue(contract["rules"]["watched_changes_after_delta_source_main_must_report_stale_on_main"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

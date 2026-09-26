import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v330_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v330.json"
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT.json"

BASE_PRS = {206, 207, 208, 209, 210, 213, 216, 217, 218}
DELTA_PRS = {227, 230, 234, 238, 243, 245, 249, 263, 273, 278, 279}
EXPECTED_NEW_LESSONS = {
    "TABLET-GPT-AUTO-MAIN-READINESS-V295",
    "TABLET-GPT-PRICE-PROVENANCE-RUNTIME-BUNDLE-V296-V300",
    "TABLET-GPT-EDITION-OCR-GENERATION-MARKET-V302-V309",
    "TABLET-GPT-PROTECTED-DATA-DRIVE-CADENCE-V305-V306",
    "TABLET-GPT-VERIFIED-LEARNING-REGION-TXN-V309",
    "TABLET-GPT-SYNC-TRUST-BOUNDARY-V319",
    "TABLET-GPT-CARD-CLASSIFICATION-EXACT-BINDING-V320-V327",
    "TABLET-GPT-FX-FRESHNESS-FAILCLOSED-V328-V329",
}


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(rows):
    raw = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _id_digest(ids):
    raw = json.dumps(ids, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV330(unittest.TestCase):
    def setUp(self):
        self.base = _load(BASE)
        self.delta = _load(DELTA)
        self.receipt = _load(RECEIPT)
        self.contract = _load(CONTRACT)

    def test_base_history_is_preserved_and_delta_is_exact(self):
        self.assertEqual(self.base["lesson_digest_sha256"], self.delta["base_lesson_digest_sha256"])
        self.assertEqual(self.base["lesson_digest_sha256"], self.receipt["base_lesson_digest_sha256"])
        calculated = _digest(self.delta["lessons"])
        self.assertEqual(calculated, self.delta["lesson_digest_sha256"])
        self.assertEqual(calculated, self.receipt["delta_lesson_digest_sha256"])
        self.assertEqual(13, len(self.base["lessons"]))
        self.assertEqual(8, len(self.delta["lessons"]))

    def test_combined_ids_and_contract_are_exact(self):
        ids = [row["lesson_id"] for row in self.base["lessons"]] + [
            row["lesson_id"] for row in self.delta["lessons"]
        ]
        self.assertEqual(21, len(ids))
        self.assertEqual(21, len(set(ids)))
        self.assertEqual(ids, self.receipt["accepted_lesson_ids"])
        self.assertEqual(_id_digest(ids), self.delta["combined_lesson_id_digest_sha256"])
        self.assertEqual(_id_digest(ids), self.receipt["combined_lesson_id_digest_sha256"])
        self.assertEqual(21, self.contract["current_required_lesson_count"])
        self.assertEqual(13, self.contract["base_required_lesson_count"])
        self.assertEqual(8, self.contract["delta_required_lesson_count"])
        self.assertTrue(EXPECTED_NEW_LESSONS.issubset(set(ids)))

    def test_merge_provenance_covers_current_tablet_and_card_hardening(self):
        self.assertEqual(BASE_PRS, {row["pr"] for row in self.base["covered_merges"]})
        self.assertEqual(DELTA_PRS, {row["pr"] for row in self.delta["covered_merges"]})
        self.assertEqual(BASE_PRS | DELTA_PRS, set(self.contract["current_required_merge_prs"]))
        by_pr = {row["pr"]: row for row in self.delta["covered_merges"]}
        self.assertEqual("e67694073c8b6c73ed8f1aa06942345a2403dc3c", by_pr[227]["merge_sha"])
        self.assertEqual("ec9d2849355261a4c572edeeae73fc8b002627c7", by_pr[263]["merge_sha"])
        self.assertEqual("19467f564e7ca5408af4f31137ec60b0b837f7b0", by_pr[273]["merge_sha"])
        self.assertEqual("279fec44f3064332bcfc02c868f80c2cfd67fa18", by_pr[279]["merge_sha"])
        self.assertEqual(by_pr[279]["merge_sha"], self.delta["source_main_sha"])

    def test_safe_share_and_learning_boundaries_remain_fail_closed(self):
        self.assertEqual(self.delta["source_repository"], self.receipt["source_repository"])
        self.assertEqual(self.delta["source_main_sha"], self.receipt["source_main_sha"])
        self.assertRegex(self.delta["source_main_sha"], r"^[0-9a-f]{40}$")
        policy = self.delta["share_policy"]
        self.assertFalse(policy["chatgpt_model_weights_exported"])
        self.assertFalse(policy["raw_grading_calibration_shared"])
        self.assertFalse(policy["device_local_runtime_memory_overwritten"])
        self.assertTrue(policy["peer_verified_never_auto_promotes_local"])
        receipt_policy = self.receipt["alignment_policy"]
        self.assertTrue(receipt_policy["device_local_learning_state_merge_required"])
        self.assertTrue(receipt_policy["blind_overwrite_forbidden"])
        self.assertTrue(receipt_policy["grading_calibration_auto_import_forbidden"])
        self.assertTrue(receipt_policy["future_watched_main_changes_require_new_delta"])

    def test_new_lessons_are_verified_high_confidence(self):
        rows = {row["lesson_id"]: row for row in self.delta["lessons"]}
        self.assertEqual(EXPECTED_NEW_LESSONS, set(rows))
        for row in rows.values():
            self.assertEqual("passed", row["verification_result"])
            self.assertIs(row["regression_pass"], True)
            self.assertEqual("high", row["confidence_level"])
            self.assertEqual("both", row["applicable_scope"])

    def test_freshness_watch_cannot_silently_ignore_sync_drift(self):
        watch = self.contract["freshness_watch"]
        self.assertEqual("17 */6 * * *", watch["schedule_cron_utc"])
        self.assertIn("tablet_runtime_manifest.py", watch["exact_paths"])
        self.assertIn("index.html", watch["exact_paths"])
        self.assertIn(".github/workflows/tablet-", watch["path_prefixes"])
        excluded = set(watch["exclude_paths"])
        self.assertIn("integrity_manifest.json", excluded)
        self.assertIn("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v330_delta.json", excluded)
        self.assertNotIn("tablet_runtime_manifest.py", excluded)
        self.assertTrue(self.contract["rules"]["watched_changes_after_delta_source_main_must_report_stale_on_main"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

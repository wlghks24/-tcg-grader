import hashlib
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v350_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v351_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v351.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V350.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V351.json"
SOURCE = "c649f79f3183d615171a79a89af8731cc19c2398"
EXPECTED_DIGEST = "dd0c8324df37e0e3e7a1797f9c22b0d1dec828b9881f82ac229e12ce13d98eb2"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TabletGptTcgGraderSyncV351(unittest.TestCase):
    def test_postmerge_checkpoint_lineage_digest_and_safe_receipt(self):
        prior, delta, receipt, prior_contract, contract = map(
            read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT)
        )
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual(SOURCE, delta["source_main_sha"])
        self.assertEqual(SOURCE, receipt["source_main_sha"])
        self.assertEqual([320], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(SOURCE, delta["covered_merges"][0]["merge_sha"])
        self.assertEqual(
            set(contract["current_required_merge_prs"]),
            set(prior_contract["current_required_merge_prs"]) | {320},
        )
        self.assertEqual(
            prior_contract["current_required_lesson_count"],
            contract["prior_required_lesson_count"],
        )
        self.assertEqual(
            contract["prior_required_lesson_count"] + contract["delta_required_lesson_count"],
            contract["current_required_lesson_count"],
        )
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(EXPECTED_DIGEST, digest)
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"])
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertFalse(delta["share_policy"]["chatgpt_model_weights_exported"])
        self.assertFalse(delta["share_policy"]["raw_grading_calibration_shared"])
        self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])
        subprocess.run(["git", "merge-base", "--is-ancestor", SOURCE, "HEAD"], check=True)

    def test_checkpoint_makes_nonwatched_playgo_followup_fresh_without_weakening_watch(self):
        contract = read(CONTRACT)
        self.assertNotIn("candidate_sync", contract)
        self.assertTrue(contract["rules"]["post_merge_checkpoint_must_anchor_future_pr_freshness"])
        self.assertTrue(contract["rules"]["subsequent_watched_change_requires_new_generation"])
        watch = contract["freshness_watch"]
        exact = set(watch["exact_paths"])
        prefixes = tuple(watch["path_prefixes"])
        excluded = set(watch["exclude_paths"])

        def watched(path):
            return path not in excluded and (path in exact or path.startswith(prefixes))

        self.assertTrue(watched(".github/workflows/gpt-tcg-drive-package.yml"))
        self.assertTrue(watched("multi_market_price_collector.py"))
        self.assertTrue(watched("grading_company_updates.json"))
        self.assertFalse(watched("update_promo_events.py"))
        self.assertFalse(watched("promo_events.json"))
        self.assertFalse(watched("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v351_delta.json"))
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", f"{SOURCE}..HEAD"], text=True
        ).splitlines()
        relevant = sorted(path for path in changed if watched(path))
        self.assertEqual([], relevant)

    def test_latest_generation_is_complete_and_bound(self):
        contract = read(CONTRACT)
        expected = {
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v351_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v351.json",
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V351.json",
            "test_tablet_gpt_tcg_grader_sync_v351.py",
        }
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v351_delta.json", contract["delta_snapshot"])
        self.assertEqual("TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v351.json", contract["receiver_receipt"])
        self.assertEqual("test_tablet_gpt_tcg_grader_sync_v351.py", contract["verification_test"])
        self.assertTrue(expected.issubset(set(contract["freshness_watch"]["exclude_paths"])))
        for path in expected:
            self.assertTrue((ROOT / path).is_file(), path)


if __name__ == "__main__":
    unittest.main(verbosity=2)

import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v341_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v342_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v342.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V341.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V342.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TabletGptTcgGraderSyncV342(unittest.TestCase):
    def test_lineage_digest_and_exact_base(self):
        prior, delta, receipt, prior_contract, contract = map(read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT))
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual("e6c09a75f5906aa4b7490577decebb1dc424e2f8", delta["source_main_sha"])
        self.assertEqual(delta["source_main_sha"], receipt["source_main_sha"])
        self.assertEqual([299], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(set(contract["current_required_merge_prs"]), set(prior_contract["current_required_merge_prs"]) | {299})
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in delta["lessons"]], receipt["accepted_lesson_ids"])
        self.assertTrue(all(row["regression_pass"] for row in delta["lessons"]))
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertFalse(receipt["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(receipt["verification"]["physical_drive_readback_verified"])

    def test_candidate_runtime_fixes_are_explicitly_verified(self):
        runtime_test = (ROOT / "test_runtime_hardening_v342.py").read_text(encoding="utf-8")
        scheduled = (ROOT / "TABLET_SCHEDULED_UPDATE.sh").read_text(encoding="utf-8")
        service_worker = (ROOT / "sw.js").read_text(encoding="utf-8")
        for token in (
            'pid_matches_mode()',
            'SCHEDULER_VERSION="daily-2300-kst-v3"',
            'BOOT_LOOP_HEARTBEAT_AT=$(now)',
            'run_and_reconcile_schedule()',
        ):
            self.assertIn(token, scheduled)
        exact = 'const exact=await caches.match(request);'
        broad = 'const cached=await caches.match(request,{ignoreSearch:true});'
        self.assertIn(exact, service_worker)
        self.assertIn(broad, service_worker)
        self.assertLess(service_worker.index(exact), service_worker.index(broad))
        self.assertIn("test_scheduler_does_not_kill_unrelated_pid", runtime_test)
        self.assertIn("test_heartbeat_preserves_loop_start_and_tracks_current_heartbeat", runtime_test)
        self.assertIn("test_pwa_exact_fallback_precedes_query_agnostic_fallback", runtime_test)

    def test_generation_files_are_bound_and_excluded(self):
        contract = read(CONTRACT)
        watch = contract["freshness_watch"]
        expected = {
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v342_delta.json",
            "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v342.json",
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V342.json",
            "test_tablet_gpt_tcg_grader_sync_v342.py",
        }
        self.assertTrue(expected.issubset(set(watch["exclude_paths"])))
        self.assertFalse(contract["rules"]["pull_request_freshness_check_is_nonblocking"])
        self.assertTrue(contract["rules"]["pull_request_candidate_sync_requires_exact_base_and_generation_files"])
        workflow = (ROOT / ".github/workflows/tablet-gpt-tcg-grader-main-alignment.yml").read_text(encoding="utf-8")
        for token in ("GITHUB_EVENT_PATH", "generation_files.issubset(pr_changed)", "source == base_sha", "TABLET_GPT_PR_SYNC_CANDIDATE_COVERED"):
            self.assertIn(token, workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)

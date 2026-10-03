import hashlib
import json
import unittest
from pathlib import Path

from sync_v376_successor_test_support import assert_v405_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V405.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v405_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v405.json"
SCHEDULER = ROOT / "TABLET_SCHEDULED_UPDATE.sh"
BASE_SHA = "f24d5a127de9ad56431b0b9566c021956b954e65"
CANDIDATE_SHA = "7b66ee36088ebd08640d5d42ebdc60c9330cc3ac"
LESSON_ID = "TABLET-GPT-SCHEDULED-VERIFIED-AUTONOMY-V405"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV405Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_merge_lineage(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V404.json", c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v404_delta.json", c["prior_delta_snapshot"])
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(97, c["prior_required_lesson_count"])
        self.assertEqual(98, c["current_required_lesson_count"])
        self.assertIn(418, c["current_required_merge_prs"])
        self.assertEqual("SYNCED_VERIFIED", r["status"])

    def test_v405_scheduled_autonomy_contract_is_fail_closed(self):
        c = load(CONTRACT)
        for key in (
            "scheduled_autonomy_v405_daily_after_update_check_required",
            "scheduled_autonomy_v405_manifest_preflight_required",
            "scheduled_autonomy_v405_v400_self_test_required",
            "scheduled_autonomy_v405_existing_verified_entrypoint_only",
            "scheduled_autonomy_v405_fail_closed_existing_policy_required",
            "scheduled_autonomy_v405_status_and_log_required",
            "scheduled_autonomy_v405_source_code_write_forbidden",
            "scheduled_autonomy_v405_git_write_forbidden",
        ):
            self.assertIs(c["rules"][key], True, key)

    def test_candidate_exactly_covers_scheduler_runtime_change(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(["TABLET_SCHEDULED_UPDATE.sh"], candidate["watched_paths"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        assert_v405_successor(self)

    def test_scheduler_runs_existing_verified_autonomy_entrypoint(self):
        s = SCHEDULER.read_text(encoding="utf-8")
        update = s.index("run_update || rc=$?")
        autonomy = s.index("run_autonomy_cycle || autonomy_rc=$?")
        reconcile = s.index("ensure_schedule || true", autonomy)
        self.assertLess(update, autonomy)
        self.assertLess(autonomy, reconcile)
        self.assertIn('python "$ROOT/tablet_runtime_manifest.py" --check --compile', s)
        self.assertIn('python "$ROOT/tablet_autonomous_evolution_v400.py" --self-test', s)
        self.assertIn("python tablet_autonomous_evolution_v400.py --domain tablet_gpt --execute-safe-learning --apply-capabilities --train-meta --apply-skills", s)
        self.assertIn("AUTONOMY_STATUS_FILE=", s)
        self.assertNotIn("git push", s)

    def test_receipt_preserves_device_and_source_boundaries(self):
        r = load(RECEIPT)
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])
        self.assertFalse(r["alignment_policy"]["source_code_auto_generation"])
        self.assertFalse(r["alignment_policy"]["runtime_ui_source_auto_rewrite"])
        self.assertFalse(r["alignment_policy"]["git_write"])
        self.assertFalse(r["alignment_policy"]["arbitrary_command_generation"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

import hashlib
import json
import unittest
from pathlib import Path

from sync_v376_successor_test_support import assert_v406_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V406.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v406_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v406.json"
SCHEDULER = ROOT / "TABLET_SCHEDULED_UPDATE.sh"
BASE_SHA = "13b3925ff2242bfe1f560df1ec3b4fcf8afabfab"
CANDIDATE_SHA = "4e349f0f1e1a9d8a6ed4878305d26378bdd71e82"
LESSON_ID = "TABLET-GPT-AUTONOMY-STATUS-ATOMIC-WRITE-V406"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV406Tests(unittest.TestCase):
    def test_generation_binding_digest_counts_and_merge_lineage(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V405.json", c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v405_delta.json", c["prior_delta_snapshot"])
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(98, c["prior_required_lesson_count"])
        self.assertEqual(99, c["current_required_lesson_count"])
        self.assertIn(419, c["current_required_merge_prs"])
        self.assertEqual("SYNCED_VERIFIED", r["status"])

    def test_v406_atomic_status_contract_is_fail_closed(self):
        c = load(CONTRACT)
        for key in (
            "autonomy_status_v406_pid_qualified_temp_required",
            "autonomy_status_v406_atomic_rename_required",
            "autonomy_status_v406_literal_dollar_temp_forbidden",
            "scheduled_autonomy_v405_semantics_unchanged_required",
        ):
            self.assertIs(c["rules"][key], True, key)

    def test_candidate_exactly_covers_scheduler_fix(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(["TABLET_SCHEDULED_UPDATE.sh"], candidate["watched_paths"])
        assert_v406_successor(self)

    def test_scheduler_uses_pid_qualified_atomic_status_temp(self):
        s = SCHEDULER.read_text(encoding="utf-8")
        self.assertIn('tmp="${AUTONOMY_STATUS_FILE}.tmp.$$"', s)
        self.assertNotIn('tmp="${AUTONOMY_STATUS_FILE}.tmp.$"', s)
        self.assertIn('mv "$tmp" "$AUTONOMY_STATUS_FILE"', s)
        self.assertIn("run_autonomy_cycle || autonomy_rc=$?", s)
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

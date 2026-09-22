import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
SNAPSHOT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt.json"
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT.json"

EXPECTED_PRS = {206, 207, 208, 209, 210, 213, 216, 217, 218}
EXPECTED_NEW_LESSONS = {
    "TABLET-GPT-RUNTIME-PROCESS-IDENTITY-V286",
    "TABLET-GPT-GRADE-LEARNING-STORE-TXN-V287",
    "TABLET-GPT-MANUAL-REGISTRY-TXN-V288",
}


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _lesson_digest(lessons):
    raw = json.dumps(lessons, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV289(unittest.TestCase):
    def setUp(self):
        self.snapshot = _load(SNAPSHOT)
        self.receipt = _load(RECEIPT)
        self.contract = _load(CONTRACT)

    def test_current_digest_and_ids_exactly_match(self):
        calculated = _lesson_digest(self.snapshot["lessons"])
        self.assertEqual(calculated, self.snapshot["lesson_digest_sha256"])
        self.assertEqual(calculated, self.receipt["source_lesson_digest_sha256"])
        source_ids = [row["lesson_id"] for row in self.snapshot["lessons"]]
        self.assertEqual(source_ids, self.receipt["accepted_lesson_ids"])
        self.assertEqual(len(source_ids), 13)
        self.assertEqual(len(source_ids), len(set(source_ids)))
        self.assertTrue(EXPECTED_NEW_LESSONS.issubset(set(source_ids)))

    def test_current_merge_provenance_exactly_covers_v286_to_v288(self):
        rows = self.snapshot["covered_merges"]
        self.assertEqual(EXPECTED_PRS, {row["pr"] for row in rows})
        by_pr = {row["pr"]: row for row in rows}
        self.assertEqual("50b31177216e300107b6187a7bf84238da93ae17", by_pr[216]["merge_sha"])
        self.assertEqual("acca7b8e1f6c1443e7eb9cea800651e4a4fc134b", by_pr[217]["merge_sha"])
        self.assertEqual("21083d72d82e5e8559eb45607374714958146876", by_pr[218]["merge_sha"])
        self.assertEqual([*sorted(EXPECTED_PRS)], self.contract["current_required_merge_prs"])
        self.assertEqual(13, self.contract["current_required_lesson_count"])

    def test_provenance_and_safe_share_boundary(self):
        self.assertEqual(self.snapshot["source_repository"], self.receipt["source_repository"])
        self.assertEqual(self.snapshot["source_main_sha"], self.receipt["source_main_sha"])
        self.assertRegex(self.snapshot["source_main_sha"], r"^[0-9a-f]{40}$")
        policy = self.snapshot["share_policy"]
        self.assertFalse(policy["chatgpt_model_weights_exported"])
        self.assertFalse(policy["raw_grading_calibration_shared"])
        self.assertFalse(policy["device_local_runtime_memory_overwritten"])
        self.assertTrue(policy["peer_verified_never_auto_promotes_local"])
        receipt_policy = self.receipt["alignment_policy"]
        self.assertTrue(receipt_policy["device_local_learning_state_merge_required"])
        self.assertTrue(receipt_policy["blind_overwrite_forbidden"])
        self.assertTrue(receipt_policy["grading_calibration_auto_import_forbidden"])

    def test_new_lessons_are_verified_and_high_confidence(self):
        rows = {row["lesson_id"]: row for row in self.snapshot["lessons"]}
        for lesson_id in EXPECTED_NEW_LESSONS:
            row = rows[lesson_id]
            self.assertEqual("passed", row["verification_result"])
            self.assertIs(row["regression_pass"], True)
            self.assertEqual("high", row["confidence_level"])
            self.assertEqual("both", row["applicable_scope"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

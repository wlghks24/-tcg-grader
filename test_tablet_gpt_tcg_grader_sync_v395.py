import hashlib
import json
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v400 as autonomy
from sync_v376_successor_test_support import assert_v395_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V395.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v395_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v395.json"
BASE_SHA = "90fc86cd1fa0d5594d52f57e89b345003859aba5"
CANDIDATE_SHA = "5f36e0737976567a5069520961ca56b23028d964"
LESSON_ID = "TABLET-GPT-CURRENT-RUNTIME-CARD-VERIFICATION-V395"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV395Tests(unittest.TestCase):
    def test_generation_binding_digest_and_counts(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual(
            "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V394.json",
            c["prior_contract"],
        )
        self.assertEqual(
            "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v394_delta.json",
            c["prior_delta_snapshot"],
        )
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(87, c["prior_required_lesson_count"])
        self.assertEqual(88, c["current_required_lesson_count"])
        self.assertIn(404, c["current_required_merge_prs"])
        self.assertEqual(405, c["current_required_merge_prs"][-1])
        self.assertEqual("SYNCED_VERIFIED", r["status"])

    def test_v395_rules_keep_current_runtime_verification_fail_closed(self):
        c = load(CONTRACT)
        for key in (
            "current_runtime_card_verification_preferred_required",
            "current_runtime_card_verification_required_checks_required",
            "incomplete_current_runtime_verification_not_promoted_required",
            "historical_v109_audit_fallback_only_required",
            "missing_card_measurement_verification_revalidation_required",
            "v399_gate_cannot_be_bypassed",
            "autonomous_source_code_generation_forbidden",
            "autonomous_git_write_forbidden",
            "market_direction_invention_forbidden",
        ):
            self.assertIs(c["rules"][key], True, key)
        self.assertTrue(autonomy.SAFETY["current_runtime_verification_preferred"])
        self.assertTrue(autonomy.SAFETY["historical_v109_audit_fallback_only"])
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_candidate_exactly_covers_current_runtime_card_verification_change(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(["tablet_autonomous_evolution_v400.py"], candidate["watched_paths"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        assert_v395_successor(self)

    def test_receipt_preserves_physical_device_boundary(self):
        r = load(RECEIPT)
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])
        self.assertTrue(r["alignment_policy"]["current_runtime_card_verification_preferred"])
        self.assertTrue(r["alignment_policy"]["current_runtime_required_checks_fail_closed"])
        self.assertFalse(r["alignment_policy"]["incomplete_current_runtime_verification_auto_promotion"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

import hashlib
import json
import unittest
from pathlib import Path

import tablet_autonomous_evolution_v400 as autonomy
import tablet_runtime_manifest as manifest
from sync_v376_successor_test_support import assert_v397_successor

ROOT = Path(__file__).resolve().parent
CONTRACT = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V397.json"
DELTA = ROOT / "TCG_CROSSCHECK" / "TABLET_GPT" / "learning_snapshot_v397_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK" / "TCG_GRADER" / "tablet_gpt_learning_receipt_v397.json"
BASE_SHA = "624b5e678f9360de308a5d06a56dc4b69c27c16c"
CANDIDATE_SHA = "5866641db9d97d644835b409bc0b10a9f93d4d89"
LESSON_ID = "TABLET-GPT-FULL-CONTROL-PLANE-V397"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class TabletGptTcgGraderSyncV397Tests(unittest.TestCase):
    def test_generation_binding_digest_and_counts(self):
        c, d, r = load(CONTRACT), load(DELTA), load(RECEIPT)
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V396.json", c["prior_contract"])
        self.assertEqual("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v396_delta.json", c["prior_delta_snapshot"])
        self.assertEqual(BASE_SHA, d["source_main_sha"])
        self.assertEqual(BASE_SHA, r["source_main_sha"])
        self.assertEqual(d["lesson_digest_sha256"], digest(d["lessons"]))
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([LESSON_ID], r["accepted_lesson_ids"])
        self.assertEqual(89, c["prior_required_lesson_count"])
        self.assertEqual(90, c["current_required_lesson_count"])
        self.assertEqual(407, c["current_required_merge_prs"][-1])
        self.assertEqual("SYNCED_VERIFIED", r["status"])

    def test_full_tablet_control_plane_is_fail_closed(self):
        c = load(CONTRACT)
        for key in (
            "tablet_control_plane_single_ssot_required",
            "tablet_control_plane_fail_closed_startup_required",
            "tablet_control_plane_ci_coverage_required",
            "tablet_pwa_entry_fail_closed_required",
            "tablet_ops_full_manifest_scoring_required",
            "tablet_audit_entrypoint_required",
            "drive_sync_control_plane_required",
            "physical_device_verification_separate_required",
            "autonomous_source_code_generation_forbidden",
            "autonomous_git_write_forbidden",
            "market_direction_invention_forbidden",
        ):
            self.assertIs(c["rules"][key], True, key)
        active = set(manifest.ACTIVE_RUNTIME_FILES)
        self.assertTrue(set(manifest.TABLET_CONTROL_PLANE_FILES).issubset(active))
        self.assertTrue(set(manifest.TABLET_PWA_ENTRY_FILES).issubset(active))
        self.assertFalse(autonomy.SAFETY["source_code_auto_generation"])
        self.assertFalse(autonomy.SAFETY["git_write"])
        self.assertFalse(autonomy.SAFETY["market_direction_inferred"])

    def test_candidate_exactly_covers_full_control_plane_change(self):
        c = load(CONTRACT)
        candidate = c["candidate_sync"]
        self.assertEqual(BASE_SHA, candidate["base_main_sha"])
        self.assertEqual(CANDIDATE_SHA, candidate["candidate_commit"])
        self.assertEqual(["VERIFY_TABLET_FINAL.sh","main","tablet_autonomous_evolution_v400.py","tablet_runtime_manifest.py"], candidate["watched_paths"])
        self.assertTrue(candidate["requires_exact_watched_path_match"])
        self.assertTrue(candidate["post_merge_coverage_allowed"])
        assert_v397_successor(self)

    def test_receipt_preserves_physical_device_boundary(self):
        r = load(RECEIPT)
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])
        self.assertFalse(r["verification"]["physical_drive_readback_verified"])
        self.assertTrue(r["verification"]["device_reverification_required"])
        self.assertTrue(r["alignment_policy"]["complete_tablet_control_plane_manifest_required"])
        self.assertTrue(r["alignment_policy"]["fail_closed_partial_runtime_start_required"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

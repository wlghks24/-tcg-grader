import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v331_delta.json"
DELTA = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v334_delta.json"
RECEIPT = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v334.json"
PRIOR_CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V331.json"
CONTRACT = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V334.json"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


class TabletGptTcgGraderSyncV334(unittest.TestCase):
    def test_verified_ui_lessons_and_source_lineage(self):
        prior, delta, receipt, prior_contract, contract = map(
            read, (PRIOR, DELTA, RECEIPT, PRIOR_CONTRACT, CONTRACT)
        )
        self.assertEqual(prior["lesson_digest_sha256"], delta["prior_lesson_digest_sha256"])
        self.assertEqual(delta["prior_lesson_digest_sha256"], receipt["prior_lesson_digest_sha256"])
        self.assertEqual(delta["schema_version"], receipt["schema_version"])
        self.assertEqual(delta["schema_version"], contract["schema_version"])
        self.assertEqual(delta["source_repository"], receipt["source_repository"])
        self.assertEqual(delta["source_main_sha"], receipt["source_main_sha"])
        self.assertEqual("a4c43b6c8fe495d2eec2808d543f3b8e74db0542", delta["source_main_sha"])
        self.assertEqual([283, 284, 285, 286, 287], [row["pr"] for row in delta["covered_merges"]])
        self.assertEqual(
            set(contract["current_required_merge_prs"]),
            set(prior_contract["current_required_merge_prs"]) | {283, 284, 285, 286, 287},
        )

    def test_lesson_digest_and_safe_receipt(self):
        delta, receipt, contract = map(read, (DELTA, RECEIPT, CONTRACT))
        raw = json.dumps(delta["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self.assertEqual(digest, delta["lesson_digest_sha256"])
        self.assertEqual(digest, receipt["delta_lesson_digest_sha256"])
        self.assertEqual(2, len(delta["lessons"]))
        lesson_ids = [row["lesson_id"] for row in delta["lessons"]]
        self.assertEqual(lesson_ids, receipt["accepted_lesson_ids"])
        self.assertEqual(
            ["TABLET-GPT-UI-STATE-BOUNDARIES-V333", "TABLET-GPT-IPHONE-RELEASE-LAYOUT-V334"],
            lesson_ids,
        )
        self.assertTrue(all(row["regression_pass"] for row in delta["lessons"]))
        self.assertTrue(all(row["confidence_level"] == "high" for row in delta["lessons"]))
        self.assertEqual("SYNCED_VERIFIED", receipt["status"])
        self.assertEqual(24, contract["current_required_lesson_count"])
        self.assertFalse(delta["share_policy"]["chatgpt_model_weights_exported"])
        self.assertFalse(delta["share_policy"]["raw_grading_calibration_shared"])
        self.assertFalse(delta["share_policy"]["device_local_runtime_memory_overwritten"])
        self.assertTrue(receipt["alignment_policy"]["blind_overwrite_forbidden"])
        self.assertTrue(receipt["alignment_policy"]["peer_verified_never_auto_promotes_local"])
        self.assertFalse(receipt["verification"]["device_visual_rendering_verified"])
        self.assertTrue(receipt["verification"]["device_visual_reverification_required"])

    def test_active_iphone_layout_delivery_and_freshness_watch(self):
        html = (ROOT / "index.html").read_text(encoding="utf-8")
        css = (ROOT / "ui_tablet_refine_v122.css").read_text(encoding="utf-8")
        contract = read(CONTRACT)
        self.assertIn('href="ui_tablet_refine_v122.css?v=122"', html)
        self.assertIn("@media(max-width:539px)", css)
        self.assertIn(".release-top{", css)
        self.assertIn("display:grid!important", css)
        self.assertIn("grid-template-columns:minmax(0,1fr)!important", css)
        self.assertIn(".release-name{", css)
        self.assertIn("word-break:keep-all!important", css)
        self.assertIn(".release-badge{", css)
        self.assertIn("white-space:normal!important", css)
        watch = contract["freshness_watch"]
        for path in ("index.html", "ui_tablet_refine_v122.css", "ui_app_shell_v272.css", "ui_app_shell_v272.js", "sw.js"):
            self.assertIn(path, watch["exact_paths"])
            self.assertNotIn(path, watch["exclude_paths"])
        self.assertIn("TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v334_delta.json", watch["exclude_paths"])
        self.assertTrue(contract["rules"]["watched_changes_after_delta_source_main_must_report_stale_on_main"])
        self.assertTrue(contract["rules"]["device_visual_reverification_required_for_visual_fix"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

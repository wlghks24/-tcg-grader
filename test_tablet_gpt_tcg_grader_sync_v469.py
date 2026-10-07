#!/usr/bin/env python3
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from sync_v376_successor_test_support import assert_v469_successor

ROOT = Path(__file__).resolve().parent
C = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V469.json"
D = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v469_delta.json"
R = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v469.json"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


class SyncV469(unittest.TestCase):
    def test_generation_digest_and_exact_scope(self):
        c, d, r = load(C), load(D), load(R)
        raw = json.dumps(d["lessons"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.assertEqual(d["lesson_digest_sha256"], hashlib.sha256(raw.encode("utf-8")).hexdigest())
        self.assertEqual(d["lesson_digest_sha256"], r["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in d["lessons"]], r["accepted_lesson_ids"])
        self.assertEqual(
            ["index.html", "sw.js", "tablet_runtime_manifest.py", "tcg_updater.py"],
            c["candidate_sync"]["watched_paths"],
        )
        self.assertTrue(c["candidate_sync"]["requires_exact_watched_path_match"])
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", c["candidate_sync"]["candidate_commit"], "HEAD"],
            check=True,
        )
        assert_v469_successor(self)

    def test_expanded_registry_ui_safety_contract(self):
        d, r = load(D), load(R)
        index = (ROOT / "index.html").read_text(encoding="utf-8")
        ui = (ROOT / "tcg_registry_ui_v469.js").read_text(encoding="utf-8")
        sw = (ROOT / "sw.js").read_text(encoding="utf-8")
        self.assertIn('id="tcgRegistryMarketHub"', index)
        self.assertIn("tcg_registry_ui_v469.js?v=469", index)
        self.assertIn('row.state !== "watch"', ui)
        self.assertIn("promoted_tcg_source_signals_v413.json", ui)
        self.assertIn("promoted_tcg_multisource_coverage_v432.json", ui)
        self.assertIn("tcg-v276-network-first-runtime", sw)
        self.assertFalse(d["share_policy"]["non_core_grading_auto_enable"])
        self.assertTrue(d["share_policy"]["core_three_grading_preserved"])
        self.assertTrue(r["alignment_policy"]["watch_read_only_and_live_purchase_blocked"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

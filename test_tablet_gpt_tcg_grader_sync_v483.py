#!/usr/bin/env python3
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from sync_v376_successor_test_support import assert_v483_successor

ROOT = Path(__file__).resolve().parent
C = ROOT / "TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V483.json"
D = ROOT / "TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v483_delta.json"
R = ROOT / "TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v483.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

class SyncV483(unittest.TestCase):
    def test_generation_digest_and_exact_scope(self):
        c,d,r=load(C),load(D),load(R)
        raw=json.dumps(d["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"))
        self.assertEqual(d["lesson_digest_sha256"],hashlib.sha256(raw.encode("utf-8")).hexdigest())
        self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in d["lessons"]],r["accepted_lesson_ids"])
        self.assertEqual(sorted(["purchase_sources.json","tcg_registry_ui_v469.js","ui_app_shell_v272.css","ui_app_shell_v272.js","update_purchase_sources.py"]),c["candidate_sync"]["watched_paths"])
        self.assertEqual(137,c["current_required_lesson_count"])
        subprocess.run(["git","merge-base","--is-ancestor",c["candidate_sync"]["candidate_commit"],"HEAD"],check=True)
        assert_v483_successor(self)

    def test_card_context_purchase_and_stock_boundaries(self):
        d,r=load(D),load(R)
        shell=(ROOT/"ui_app_shell_v272.js").read_text(encoding="utf-8")
        purchase=(ROOT/"update_purchase_sources.py").read_text(encoding="utf-8")
        registry_ui=(ROOT/"tcg_registry_ui_v469.js").read_text(encoding="utf-8")
        for token in ("exactSetContext","gradeCockpitPurchaseOnline","gradeCockpitPurchaseNearby","원문 가격 확인"):
            self.assertIn(token,shell)
        for token in ("주변 취급점 지도검색","inventory_verified","url_template"):
            self.assertIn(token,purchase)
        self.assertIn("window.tcgRegistryGames = publicGames",registry_ui)
        self.assertFalse(d["share_policy"]["non_core_grading_enabled"])
        self.assertFalse(d["share_policy"]["unverified_stock_invention"])
        self.assertFalse(d["share_policy"]["unverified_generation_invention"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])

if __name__=="__main__":
    unittest.main(verbosity=2)

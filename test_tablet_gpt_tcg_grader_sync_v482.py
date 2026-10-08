#!/usr/bin/env python3
import hashlib
import json
import subprocess
import unittest
from pathlib import Path

from sync_v376_successor_test_support import assert_v482_successor

ROOT=Path(__file__).resolve().parent
C=ROOT/"TCG_CROSSCHECK/TABLET_GPT_TCG_GRADER_SYNC_CONTRACT_V482.json"
D=ROOT/"TCG_CROSSCHECK/TABLET_GPT/learning_snapshot_v482_delta.json"
R=ROOT/"TCG_CROSSCHECK/TCG_GRADER/tablet_gpt_learning_receipt_v482.json"

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

class SyncV482(unittest.TestCase):
    def test_generation_digest_and_exact_scope(self):
        c,d,r=load(C),load(D),load(R)
        raw=json.dumps(d["lessons"],ensure_ascii=False,sort_keys=True,separators=(",",":"))
        self.assertEqual(d["lesson_digest_sha256"],hashlib.sha256(raw.encode("utf-8")).hexdigest())
        self.assertEqual(d["lesson_digest_sha256"],r["delta_lesson_digest_sha256"])
        self.assertEqual([row["lesson_id"] for row in d["lessons"]],r["accepted_lesson_ids"])
        self.assertEqual(sorted(["multi_market_price_collector.py","multi_market_prices.css","multi_market_prices.js"]),c["candidate_sync"]["watched_paths"])
        self.assertEqual(136,c["current_required_lesson_count"])
        subprocess.run(["git","merge-base","--is-ancestor",c["candidate_sync"]["candidate_commit"],"HEAD"],check=True)
        assert_v482_successor(self)

    def test_freshness_variant_export_and_skills_are_bound(self):
        d,r=load(D),load(R)
        collector=(ROOT/"multi_market_price_collector.py").read_text(encoding="utf-8")
        market=(ROOT/"multi_market_prices.js").read_text(encoding="utf-8")
        for token in ("price_freshness","_source_date_iso","recommendation_freshness","freshness_status"):
            self.assertIn(token,collector)
        for token in ("multiMarketVariant","downloadEvidence","multiMarketExportCsv","freshnessText"):
            self.assertIn(token,market)
        for skill in ("tcg-market-freshness","tcg-card-variant-resolution","tcg-local-evidence-export"):
            a=ROOT/".agents/skills"/skill/"SKILL.md"
            c=ROOT/".codex/skills"/skill/"SKILL.md"
            self.assertTrue(a.is_file(),skill)
            self.assertEqual(a.read_bytes(),c.read_bytes(),skill)
        self.assertFalse(d["share_policy"]["cloud_upload_enabled"])
        self.assertFalse(d["share_policy"]["unverified_price_invention"])
        self.assertFalse(r["verification"]["physical_tablet_runtime_verified"])

if __name__=="__main__":
    unittest.main(verbosity=2)

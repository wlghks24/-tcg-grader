#!/usr/bin/env python3
"""Exact V491 purchase successor with historical sync protection."""
import hashlib
import subprocess
import unittest
from pathlib import Path

from sync_v376_successor_test_support import (
    V491_PURCHASE_BASE, V491_PURCHASE_CANDIDATE,
    V491_PURCHASE_PATH, V491_PURCHASE_SHA256,
)

ROOT = Path(__file__).resolve().parent


class PurchaseSyncV491(unittest.TestCase):
    def test_exact_reviewed_market_source_and_no_historical_mutation(self):
        for commit in (V491_PURCHASE_BASE, V491_PURCHASE_CANDIDATE):
            subprocess.run(["git", "merge-base", "--is-ancestor", commit, "HEAD"],
                           check=True, cwd=ROOT, timeout=15)
        self.assertEqual(
            [],
            subprocess.check_output(
                ["git", "diff", "--name-only",
                 "1ad0c21facb403483bd39fd59ae63462290f2afa.."+V491_PURCHASE_BASE,
                 "--", V491_PURCHASE_PATH],
                cwd=ROOT, text=True, timeout=15,
            ).splitlines(),
        )
        raw = (ROOT / V491_PURCHASE_PATH).read_bytes()
        self.assertEqual(V491_PURCHASE_SHA256, hashlib.sha256(raw).hexdigest())

    def test_new_purchase_routes_are_candidate_only_not_stock_assertions(self):
        source = (ROOT / V491_PURCHASE_PATH).read_text(encoding="utf-8")
        for token in ('"type": "map"', '"channel": "offline"',
                      '"registry_generated": True', '"inventory_verified": False',
                      '"inventory_status": UNVERIFIED_INVENTORY'):
            self.assertIn(token, source)


if __name__ == "__main__":
    unittest.main()

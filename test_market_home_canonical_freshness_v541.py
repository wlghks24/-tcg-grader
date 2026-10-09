#!/usr/bin/env python3
"""V541: market home must match core 2/7/30-day KST source freshness."""
from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from market_price_context_v433 import price_freshness

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "tcg_market_expanded_v487.js"


class CanonicalMarketHomeV541(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = SOURCE.read_text(encoding="utf-8")

    def test_canonical_contract_wired_without_new_network_calls(self):
        src = self.js
        reference = (ROOT / "market_price_context_v433.py").read_text(encoding="utf-8")
        self.assertIn("MARKET_DAY_ZONE=timezone(timedelta(hours=9))", reference)
        for predicate in ("age<=2", "age<=7", "age<=30"):
            with self.subTest(predicate=predicate):
                self.assertIn(predicate, reference)
                self.assertIn(predicate, src)
        for status in ("FRESH", "AGING", "STALE", "EXPIRED", "FUTURE", "INVALID", "UNKNOWN"):
            self.assertIn('"' + status + '"', src)
        self.assertIn("new Date(referenceDate.getTime() + 9 * 3600000)", src)
        self.assertNotIn('days > 14', src)
        date_region = src.split("  function marketHomeDateState(", 1)[1].split(
            "  function protectMarketHomeLinks()", 1
        )[0]
        self.assertNotIn("fetch(", date_region)
        self.assertIn('date.dataset.marketSourceLabel', src)
        self.assertIn('date.dataset.dateStatus = status', src)

    @unittest.skipUnless(shutil.which("node"), "Node.js required for executable cross-language check")
    def test_actual_javascript_matches_python_0_2_3_7_8_14_30_31(self):
        today = date(2026, 10, 9)
        ages = (0, 2, 3, 7, 8, 14, 30, 31)
        cases = [f"자료일 {(today - timedelta(days=age)).isoformat()}" for age in ages]
        start = self.js.index("  function marketHomeDateState(")
        end = self.js.index("  function protectMarketHomeLinks()", start)
        # UTC 2026-10-08 15:10 = KST 2026-10-09 00:10.
        harness = """
const assert=require('node:assert/strict');
const ref=new Date('2026-10-08T15:10:00Z');
const keys=CASES;
const rows=keys.map(label => marketHomeDateState(label,ref));
assert.equal(verifiedMarketHomeDate('자료일 2026-10-09',ref),true);
assert.equal(verifiedMarketHomeDate('자료일 2026-10-10',ref),false);
assert.equal(marketHomeSourceAgeDays('자료일 2026-10-08',ref),1);
const bad=['자료일 2026-02-31','자료일 2025-02-29','자료일 2026-04-31'];
for (const label of bad) assert.equal(marketHomeDateState(label,ref).status,'INVALID');
assert.equal(marketHomeDateState('자료일 2026-10-10',ref).status,'FUTURE');
assert.equal(marketHomeDateState('거래·관측일 미확인',ref).status,'UNKNOWN');
const beforeKstMidnight=new Date('2026-10-08T14:59:59Z');
const afterKstMidnight=new Date('2026-10-08T15:00:01Z');
assert.equal(marketHomeDateState('자료일 2026-10-09',beforeKstMidnight).status,'FUTURE');
assert.equal(marketHomeDateState('자료일 2026-10-09',afterKstMidnight).status,'FRESH');
console.log(JSON.stringify(rows));
""".replace("CASES", json.dumps(cases, ensure_ascii=False))
        run = subprocess.run(
            ["node", "-e", self.js[start:end] + harness],
            cwd=ROOT, capture_output=True, text=True, check=False, timeout=15
        )
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        results = json.loads(run.stdout)
        self.assertEqual(len(results), len(ages))
        for age, label, result in zip(ages, cases, results):
            with self.subTest(age=age):
                canonical = price_freshness(label.removeprefix("자료일 "), today=today)
                self.assertEqual(result["status"], canonical["status"])
                self.assertEqual(result["age"], canonical["age_days"])

    @unittest.skipUnless(shutil.which("node"), "Node.js required")
    def test_javascript_syntax(self):
        subprocess.run(["node", "--check", str(SOURCE)], check=True, timeout=15)


if __name__ == "__main__":
    unittest.main()

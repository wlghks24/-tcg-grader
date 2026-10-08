#!/usr/bin/env python3
"""V534: distinguish actual BOX release dates from market price observation dates."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class BoxDateProvenanceV534(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "box_knowledge_stats.js").read_text(encoding="utf-8")

    def test_release_date_never_falls_back_to_price_observation(self):
        self.assertIn("const d=parseDate(row?.release||row?.release_date);", self.source)
        self.assertNotIn("row?.release||row?.release_date||row?.source_date", self.source)
        self.assertIn("const age=daysOld(row?.market_observed_at||row?.source_date);", self.source)
        self.assertNotIn("const age=daysOld(row.release_date)", self.source)

    def test_real_node_date_logic_with_bad_calendar_and_future_evidence(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node not installed; static fail-closed contract still verified")
        src = self.source
        release = src[src.index("function parseDate("):src.index("function marketTradingSet(", src.index("function parseDate("))]
        age = src[src.index("function daysOld("):src.index("function freshnessPoints(", src.index("function daysOld("))]
        watch = src[src.index("function watchPoints("):src.index("function linkPoints(", src.index("function watchPoints("))]
        harness = release + "\n" + age + "\n" + watch + """
const answer = {
  impossible: parseDate('2026-02-31') === null,
  badLeap: parseDate('2027-02-29') === null,
  leap: parseDate('2028-02-29') instanceof Date,
  noRelease: releaseState({source_date:'2026-09-30'}) === 'UNKNOWN',
  actualRelease: releaseState({release_date:'2020-01-01',source_date:'2099-01-01'}) === 'RELEASED',
  upcoming: releaseState({release:'2099-01-01',source_date:'2020-01-01'}) === 'UPCOMING',
  futureAge: daysOld('2099-01-01') === 9999,
  malformedAge: daysOld('2026-02-31') === 9999,
  releaseNotActivity: watchPoints({release_date:'2099-01-01'}) === 0,
  futureNotActivity: watchPoints({source_date:'2099-01-01'}) === 0,
};
console.log(JSON.stringify(answer));
"""
        run = subprocess.run(
            [node, "-e", harness],
            cwd=ROOT,
            encoding="utf-8",
            capture_output=True,
            check=False,
            timeout=15,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(all(json.loads(run.stdout).values()), run.stdout)


if __name__ == "__main__":
    unittest.main()

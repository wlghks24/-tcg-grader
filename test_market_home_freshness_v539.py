#!/usr/bin/env python3
"""V539: saved market quote labels remain honest on a long-running local tablet."""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "tcg_market_expanded_v487.js"


class MarketHomeFreshnessV539Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = SOURCE.read_text(encoding="utf-8")

    def test_local_freshness_recheck_and_visible_states(self):
        for token in (
            'date.dataset.marketSourceLabel',
            'date.dataset.dateStatus = status',
            'result.status === "STALE"',
            'result.status === "INVALID"',
            'result.status.toLowerCase()',
            'tile.dataset.marketEvidenceStatus = status',
            'window.addEventListener("focus", recheckVisibleMarketDates)',
            'document.addEventListener("visibilitychange", recheckVisibleMarketDates)',
            'setInterval(recheckVisibleMarketDates, 60 * 60 * 1000)',
            '[data-market-evidence-status="stale"] .tcg-market-tile-price',
            '[data-market-evidence-status="invalid"] .tcg-market-tile-price',
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.js)
        date_region = self.js.split('  function verifiedMarketHomeDate(', 1)[1].split(
            '  function protectMarketHomeLinks()', 1
        )[0]
        self.assertNotIn('fetch(', date_region)

    @unittest.skipUnless(shutil.which("node"), "Node.js required for executable UI behavior")
    def test_actual_market_date_states_and_midnight_transition(self):
        js = self.js
        start = js.index('  function marketHomeDateState(')
        end = js.index('  function protectMarketHomeLinks()', start)
        implementation = js[start:end]
        harness = r"""
const assert = require('node:assert/strict');
const RealDate = Date;
let clock = RealDate.parse('2026-10-09T12:00:00Z');
globalThis.Date = class extends RealDate {
  constructor(...args) { super(...(args.length ? args : [clock])); }
  static now() { return clock; }
};
function item(label) {
  const tile = {dataset:{}};
  let writes = 0;
  let text = label;
  const date = {
    dataset: {},
    closest: selector => (assert.equal(selector, '.tcg-market-tile'), tile),
    get textContent() { return text; },
    set textContent(value) { writes++; text = value; }
  };
  return {date, tile, get writes() { return writes; }};
}
const current = item('자료일 2026-10-09');
const boundary = item('자료일 2026-10-02'); // 7 days
const stale = item('자료일 2026-09-24'); // 15 days
const invalid = item('자료일 2026-02-31');
const future = item('자료일 2026-10-10');
const unknown = item('거래·관측일 미확인');
const items = [current, boundary, stale, invalid, future, unknown];
const home = {querySelectorAll: selector =>
  (assert.equal(selector, '.tcg-market-tile-date'), items.map(x=>x.date))};
protectMarketHomeDates();
assert.equal(current.tile.dataset.marketEvidenceStatus, 'fresh');
assert.equal(boundary.tile.dataset.marketEvidenceStatus, 'aging');
assert.equal(stale.tile.dataset.marketEvidenceStatus, 'stale');
assert.equal(invalid.tile.dataset.marketEvidenceStatus, 'invalid');
assert.equal(future.tile.dataset.marketEvidenceStatus, 'future');
assert.equal(unknown.tile.dataset.marketEvidenceStatus, 'unknown');
assert.match(stale.date.textContent, /최신 시세 아님/);
assert.equal(unknown.date.textContent, '거래·관측일 미확인');
assert.equal(stale.date.dataset.marketSourceLabel, '자료일 2026-09-24');
const firstWrites = items.map(x=>x.writes);
protectMarketHomeDates();
assert.deepEqual(items.map(x=>x.writes), firstWrites, 'unchanged state must not trigger a DOM observer loop');
clock = RealDate.parse('2026-10-10T12:00:00Z');
protectMarketHomeDates();
assert.equal(boundary.tile.dataset.marketEvidenceStatus, 'stale');
assert.equal(boundary.date.dataset.marketSourceLabel, '자료일 2026-10-02');
assert.match(boundary.date.textContent, /과거 자료일 2026-10-02/);
assert.equal(invalid.date.dataset.marketSourceLabel, '자료일 2026-02-31');
console.log('PASS V539: 6 quote states, idempotence and day rollover');
"""
        result = subprocess.run(
            ["node", "-e", implementation + harness],
            cwd=ROOT, capture_output=True, text=True, check=False, timeout=15
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS V539:", result.stdout)

    @unittest.skipUnless(shutil.which("node"), "Node.js required")
    def test_market_js_syntax(self):
        subprocess.run(["node", "--check", str(SOURCE)], cwd=ROOT, check=True, timeout=15)


if __name__ == "__main__":
    unittest.main()

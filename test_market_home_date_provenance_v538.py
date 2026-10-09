#!/usr/bin/env python3
"""V538: a saved card/BOX date must not be displayed as verified if impossible."""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JS = ROOT / "tcg_market_expanded_v487.js"


class MarketHomeDateV538Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = JS.read_text(encoding="utf-8")

    def test_immutable_home_template_and_guard_wiring(self):
        source = self.source
        for token in (
            'function verifiedMarketHomeDate(label, referenceDate = new Date())',
            'function protectMarketHomeDates()',
            'date.dataset.dateStatus = "invalid"',
            'date.textContent = "자료일 검증 불가 · 가격 원문 재확인"',
            'new MutationObserver(protectMarketHomeLinks)',
            'protectMarketHomeDates();',
        ):
            with self.subTest(token=token):
                self.assertIn(token, source)
        home = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn('/* V485: Screenshot-informed, evidence-only market home.', home)
        self.assertIn('source_date:validDate(value.source_date)', home)
        self.assertNotIn("fetch(", source.split("function verifiedMarketHomeDate", 1)[1].split("function protectMarketHomeLinks", 1)[0])

    @unittest.skipUnless(shutil.which("node"), "Node.js required for executable date proof")
    def test_actual_js_rejects_invalid_future_and_malformed_calendar_days(self):
        source = self.source
        start = source.index("  function verifiedMarketHomeDate(")
        end = source.index("  function protectMarketHomeLinks()", start)
        implementation = source[start:end]
        harness = """
const assert = require('node:assert/strict');
const now = new Date(2026, 9, 9, 12, 0, 0);
const valid = ['자료일 2026-10-09', '자료일 2024-02-29', '자료일 2020-01-01'];
const invalid = ['자료일 2026-02-31', '자료일 2026-04-31',
  '자료일 2025-02-29', '자료일 2026-13-01', '자료일 2026-10-10',
  '자료일 2099-01-01', '자료일 2026-10-00', '자료일 2026-10-09<script>',
  '자료일 확인 불가', '', null];
for (const d of valid) assert.equal(verifiedMarketHomeDate(d, now), true, d);
for (const d of invalid) assert.equal(verifiedMarketHomeDate(d, now), false, String(d));
const bad = {textContent:'자료일 2026-02-31', dataset:{}};
const future = {textContent:'자료일 2099-01-01', dataset:{}};
const unknown = {textContent:'거래·관측일 미확인', dataset:{}};
const home = {querySelectorAll: () => [bad, future, unknown]};
protectMarketHomeDates();
assert.equal(bad.dataset.dateStatus, 'invalid');
assert.equal(future.dataset.dateStatus, 'invalid');
assert.match(bad.textContent, /검증 불가/);
assert.equal(unknown.textContent, '거래·관측일 미확인');
protectMarketHomeDates();
assert.match(bad.textContent, /검증 불가/);
console.log('PASS: 14 date boundary cases + idempotent DOM guard');
"""
        run = subprocess.run(["node", "-e", implementation + harness], text=True,
                             capture_output=True, cwd=ROOT, timeout=15, check=False)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn("PASS: 14 date boundary cases", run.stdout)

    @unittest.skipUnless(shutil.which("node"), "Node.js required for syntax check")
    def test_market_enhancer_syntax(self):
        subprocess.run(["node", "--check", str(JS)], cwd=ROOT, check=True, timeout=15)


if __name__ == "__main__":
    unittest.main()

"""Video-reproduced missing-price and exchange-rate display regressions; no browser."""
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which("node"), "Node.js required")
class VideoEconomicsTests(unittest.TestCase):
    def run_js(self, script):
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        names = ["finiteMoney", "normalizeGradePrices", "calculateGradingEconomics",
                 "formatProfit", "renderEconomics", "foreignKrw", "fxTimestampFresh"]
        # Whole real declarations, including template literals, up to the next declaration.
        parts = []
        for name in names:
            match = re.search(r"(?:^|\n)(function " + name + r"\([^\n]*[\s\S]*?)(?=\n(?:function |async function |[A-Za-z\[]))", page)
            self.assertIsNotNone(match, name)
            parts.append(match.group(1))
        setup = """
const assert=require('node:assert/strict');
const GRADING_COMPANIES=['PSA','BGS','CGC','TAG','BRG'];
const FX_MAX_AGE_MS=72*3600000, FX_MAX_FUTURE_SKEW_MS=6*3600000;
let fxTimestamp=new Date().toISOString(),fxUpdated='2026-11-10';
let fxRates={USD_KRW:1400,JPY_KRW:9,EUR_KRW:1500};
const escapeDisplayText=s=>String(s).replace(/[<>&]/g,'');
let input={buy:0,raw:0,gradingFee:50000,shipping:30000,prices:{},grade:10,company:'PSA'};
const result={innerHTML:''},document={getElementById:()=>result};
function economicsInput(){return input}
"""
        run = subprocess.run(["node", "-e", setup + "\n".join(parts) + script],
                             cwd=ROOT, capture_output=True, text=True, timeout=30)
        self.assertEqual(0, run.returncode, run.stderr)

    def test_missing_price_is_pending_but_verified_loss_still_displays(self):
        self.run_js(r"""
renderEconomics();
assert.match(result.innerHTML,/가격 확인 후 계산/);
assert.match(result.innerHTML,/계산 대기/);
assert.doesNotMatch(result.innerHTML,/-₩80,000|-100.0%|₩0</);
input.prices={10:50000}; renderEconomics();
assert.match(result.innerHTML,/-₩30,000/);
assert.match(result.innerHTML,/-37.5%/);
input.prices={10:100000}; renderEconomics();
assert.match(result.innerHTML,/\+₩20,000/);
assert.match(result.innerHTML,/25.0%/);
input.gradingFee=0;input.shipping=0;renderEconomics();
assert.match(result.innerHTML,/계산 대기/);
""")

    def test_fx_ranges_currencies_expiry_and_pack_total(self):
        self.run_js(r"""
assert.match(foreignKrw('$10 ~ $20'),/₩14,000 ~ ₩28,000/);
assert.match(foreignKrw('$10–20'),/₩14,000 ~ ₩28,000/);
assert.match(foreignKrw('€10'),/₩15,000/);
assert.match(foreignKrw('¥1000'),/₩9,000/);
assert.match(foreignKrw('$4.99 per pack / total $119.76'),/₩167,700/);
assert.equal(foreignKrw('$4.99 ~ $5.99 per pack / total $119.76'),'');
assert.equal(foreignKrw('$20 ~ $10'),'');
assert.equal(foreignKrw('$10 / €20'),'');
delete fxRates.EUR_KRW;assert.equal(foreignKrw('€10'),'');
fxTimestamp='2000-01-01T00:00:00Z';assert.equal(foreignKrw('$10'),'');
""")

    def test_markup_has_no_literal_newline_text_between_scripts(self):
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertNotRegex(page, r">\\n<script")


if __name__ == "__main__":
    unittest.main()

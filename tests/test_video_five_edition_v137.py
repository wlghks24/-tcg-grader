#!/usr/bin/env python3
"""V13.7: current main UI must distinguish editions and escape fetched prices."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FiveEditionVideoV137Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "index.html").read_text(encoding="utf-8")

    def test_regions_visible_in_four_independent_selectors(self):
        for id_ in ("releaseFilter","promoFilter","market12","identityRegion"):
            match = re.search(r'<select\s+id="' + id_ + r'"[^>]*>(.*?)</select>', self.html, re.S)
            self.assertIsNotNone(match,id_)
            for region in ("CN-S","CN-T"):
                self.assertIn('value="' + region + '"',match.group(1))
        self.assertIn('value="KR"', self.html)
        self.assertIn('value="JP"', self.html)
        self.assertIn('value="US"', self.html)

    def test_missing_chinese_prices_are_not_synthetic(self):
        code=self.html.split("async function v12SearchPrices()",1)[1].split('document.getElementById("search12")?.addEventListener',1)[0]
        self.assertIn('regionNeed==="CN-S"||regionNeed==="CN-T"',code)
        self.assertIn("임의로 다른 판본 가격을 표시하지 않습니다",code)
        self.assertIn('const regionNeed=document.getElementById("market12").value',code)

    def test_market_text_escapes_untrusted_value_and_official_price(self):
        code=self.html.split("async function v12SearchPrices()",1)[1].split('document.getElementById("search12")?.addEventListener',1)[0]
        self.assertIn("${escapeDisplayText(display)}${foreignKrw(display)}",code)
        self.assertIn("${escapeDisplayText(official)}${foreignKrw(official)}",code)
        self.assertNotIn("${display}${foreignKrw(display)}",code)
        self.assertNotIn("${official}${foreignKrw(official)}",code)

    def test_legacy_three_markets_still_present(self):
        # Adding display support may not silently remove existing KR/JP/US markets.
        for id_ in ("releaseFilter","promoFilter","market12"):
            match = re.search(r'<select\s+id="' + id_ + r'"[^>]*>(.*?)</select>', self.html, re.S)
            for region in ("KR","JP","US"):
                self.assertIn('value="' + region + '"',match.group(1))


if __name__ == "__main__":
    unittest.main()

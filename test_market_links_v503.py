# -*- coding: utf-8 -*-
"""Verify outbound links in TCG market prices are HTTPS and from known providers."""
from pathlib import Path
import shutil
import subprocess
import unittest
ROOT=Path(__file__).resolve().parent

class MarketLinksV503Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.script=(ROOT/"multi_market_prices.js").read_text(encoding="utf-8")

    def test_all_market_link_renderers_use_validator(self):
        source=self.script
        self.assertIn('safeMarketHref(row.url)', source)
        self.assertIn('safeMarketHref(row.sample_url)', source)
        self.assertIn('safeMarketHref(item?.url)', source)
        self.assertNotIn('href="'+'$'+'{esc(row.url)}"', source)
        self.assertNotIn('href="'+'$'+'{esc(item.url)}"', source)
        self.assertNotIn('href="'+'$'+'{esc(row.sample_url)}"', source)
        self.assertIn('원문 URL 확인 필요', source)

    def test_js_safe_link_function_and_syntax(self):
        node=shutil.which("node")
        if not node:
            self.skipTest("Node is needed; GitHub CI runs this test")
        check=subprocess.run([node,"--check",str(ROOT/"multi_market_prices.js")],capture_output=True,text=True,timeout=15)
        self.assertEqual(0,check.returncode,check.stderr)
        start=self.script.index("const MARKET_LINK_DOMAINS")
        end=self.script.index("\nfunction freshnessBadge",start)
        program="""
const assert=require('node:assert/strict');
const esc=value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
"""+self.script[start:end]+"""
for(const url of ['javascript:alert(1)','data:text/html,a','http://ebay.com/','//ebay.com/card','https://user:pass@ebay.com/card','https://evil.test/card','https://ebay.com.evil.test/card','https://localhost/card','https://127.0.0.1/card','https://ebay.com:444/card']){
 assert.equal(safeMarketHref(url),'',url);
}
assert.equal(safeMarketHref('https://www.ebay.com/itm/123?a=1&b=2'),'https://www.ebay.com/itm/123?a=1&amp;b=2');
assert.equal(safeMarketHref('https://snkrdunk.com/en/brands/pokemon'),'https://snkrdunk.com/en/brands/pokemon');
assert.equal(safeMarketHref('https://tcgdex.dev/markets-prices'),'https://tcgdex.dev/markets-prices');
"""
        run=subprocess.run([node,"-e",program],capture_output=True,text=True,timeout=15)
        self.assertEqual(0,run.returncode,run.stdout+run.stderr)

if __name__=="__main__":
    unittest.main()

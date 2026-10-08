#!/usr/bin/env python3
"""V535: stale/unknown BOX prices never masquerade as recent market activity."""
from __future__ import annotations

import json
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class RecentBoxMarketEvidenceV535(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "box_knowledge_stats.js").read_text(encoding="utf-8")

    def test_both_trading_surfaces_and_hot_use_same_gate(self):
        self.assertIn("const RECENT_MARKET_DAYS=14;", self.source)
        self.assertIn("!recentVerifiedMarketSignal(v))continue", self.source)
        self.assertIn("if(recentVerifiedMarketSignal(v))trading.add(k)", self.source)
        self.assertIn("!recentVerifiedMarketSignal(row))return false", self.source)
        self.assertIn("최근 14일 시세 확인", self.source)
        self.assertNotIn("if(priced(v))trading.add(k)", self.source)

    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for runtime verification")
    def test_actual_javascript_rejects_stale_future_unknown_and_unverified(self):
        src = self.source
        helpers = src[src.index("function parseDate("):src.index("function ensureGameToolbar(")]
        age = src[src.index("function daysOld("):src.index("function freshnessPoints(")]
        setup = """
const priced=v=>{const d=String(v?.display||'').trim();return !!d&&!/가격 확인 중|확인 중|미정/.test(d)};
function countryOfKey(k){return String(k||'').split('|')[0]||''}
function assetOfKey(k){return String(k||'').split('|')[2]||''}
function nameOfKey(k){return String(k||'').split('|')[1]||''}
function uniqueKey(c,n){return String(c)+'|'+String(n||'').trim().toLowerCase()}
"""
        cases = """
function dateAt(delta) {
 const d = new Date();d.setHours(12,0,0,0);d.setDate(d.getDate()+delta);
 return [d.getFullYear(),String(d.getMonth()+1).padStart(2,'0'),String(d.getDate()).padStart(2,'0')].join('-');
}
const good={display:'₩63,000',source_date:dateAt(-1),source:'https://pokard.io/',link_status:'정상'};
const examples={
 good:recentVerifiedMarketSignal(good),
 boundary:recentVerifiedMarketSignal({...good,source_date:dateAt(-14)}),
 stale:recentVerifiedMarketSignal({...good,source_date:dateAt(-15)}),
 veryOld:recentVerifiedMarketSignal({...good,source_date:'2020-01-01'}),
 unknown:recentVerifiedMarketSignal({...good,source_date:''}),
 malformed:recentVerifiedMarketSignal({...good,source_date:'2026-02-31'}),
 future:recentVerifiedMarketSignal({...good,source_date:dateAt(1)}),
 networkError:recentVerifiedMarketSignal({...good,link_status:'네트워크 지연'}),
 badProtocol:recentVerifiedMarketSignal({...good,source:'http://pokard.io/'}),
 credentials:recentVerifiedMarketSignal({...good,source:'https://user:pass@pokard.io/'}),
 noPrice:recentVerifiedMarketSignal({...good,display:'가격 확인 중'}),
 noLink:recentVerifiedMarketSignal({...good,source:''}),
 boxOnly:[...marketTradingSet({'KR|fresh|BOX':good,'KR|old|BOX':{...good,source_date:dateAt(-90)},'KR|hit|HIT':good})].join(',')==='KR|fresh',
};
console.log(JSON.stringify(examples));
"""
        proc = subprocess.run(
            ["node", "-e", setup + helpers + "\n" + age + "\n" + cases],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        for field in ("good", "boundary", "boxOnly"):
            self.assertTrue(result[field], field)
        for field in ("stale", "veryOld", "unknown", "malformed", "future",
                      "networkError", "badProtocol", "credentials", "noPrice", "noLink"):
            self.assertFalse(result[field], field)

    @unittest.skipUnless(shutil.which("node"), "Node.js syntax checker unavailable")
    def test_source_syntax(self):
        subprocess.run(["node", "--check", str(ROOT / "box_knowledge_stats.js")],
                       check=True, timeout=15)


if __name__ == "__main__":
    unittest.main()

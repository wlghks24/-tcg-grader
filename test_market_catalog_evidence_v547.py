#!/usr/bin/env python3
"""V547: catalog expansion uses dated evidence and exact TCG product identity."""
from __future__ import annotations
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
JS = ROOT / "market_catalog_expander.js"


class MarketCatalogEvidenceV547(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.js = JS.read_text(encoding="utf-8")

    def test_fail_closed_contract(self):
        for token in (
            "hasRecentMarketEvidence(value)",
            "if(value.link_status!=='정상')return false",
            "const age=(today-observed)/86400000",
            "if(age<0||age>14)return false",
            "item.marketTrading=hasRecentMarketEvidence(value)",
            "marketTrading:isTradingBox",
            "value.discovered_market!==true",
            "Number.isFinite(n)",
            "x.country===country&&x.name===name&&String(x.game||'')===game",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.js)

    @unittest.skipUnless(shutil.which("node"), "Node required for executable browser JS")
    def test_js_syntax(self):
        subprocess.run(["node", "--check", str(JS)], cwd=ROOT, timeout=15, check=True)

    @unittest.skipUnless(shutil.which("node"), "Node required for executable browser JS")
    def test_evidence_boundaries_and_identity(self):
        source = self.js
        marker = "if(document.readyState==='loading')"
        self.assertIn(marker, source)
        implementation = source.split(marker, 1)[0]
        harness = r"""
const assert = require('node:assert/strict');
Date.now = () => Date.parse('2026-10-08T15:01:00Z'); // 2026-10-09 KST
globalThis.COUNTRY_BOX_DATA = [
  {country:'JP',name:'Shared',game:'Pokémon',marketTrading:true},
  {country:'JP',name:'Shared',game:'ONE PIECE',marketTrading:true}
];
const good={game:'Pokémon',display:'₩50,000',source_date:'2026-10-09',
  source:'https://pokard.io/',link_status:'정상'};
assert.equal(prefFromSignal(82),'매우 높음');
assert.equal(prefFromSignal('68'),'높음');
for(const n of [NaN,Infinity,-Infinity,-1,101,'Infinity','1e999','',{},true]){
  assert.equal(prefFromSignal(n),'관찰 중',String(n));
}
assert.equal(hasRecentMarketEvidence(good),true);
assert.equal(hasRecentMarketEvidence({...good,source_date:'2026-09-25'}),true);
for(const date of ['2026-09-24','2026-10-10','2026-02-31','2026-10-09x','2026-10-09T12:00:00Z','']){
  assert.equal(hasRecentMarketEvidence({...good,source_date:date}),false,date);
}
for(const v of [
  {...good,link_status:'접속 불가 확인 (HTTP 403)'},
  {...good,source:'http://pokard.io/'},
  {...good,source:'https://alice:secret@pokard.io/'},
  {...good,source:''},
  {...good,market_observed_at:'invalid'},
  {...good,display:'가격 확인 중'},
]){
  assert.equal(hasRecentMarketEvidence(v),false,JSON.stringify(v));
}
const first=COUNTRY_BOX_DATA[0],second=COUNTRY_BOX_DATA[1];
assert.equal(addOrEnrich(null,'JP|Shared|BOX',{...good,source_date:'2026-09-24'}),false);
assert.equal(first.marketTrading,false,'old quote cannot remain trading');
assert.equal(second.marketTrading,true,'other game must not be touched');
addOrEnrich(null,'JP|Shared|BOX',good);
assert.equal(first.marketTrading,true,'verified recent quote may activate');
assert.equal(addOrEnrich(null,'JP|Shared|BOX',{...good,game:'NARUTO',discovered_market:true}),true);
assert.equal(COUNTRY_BOX_DATA.at(-1).game,'NARUTO');
assert.equal(addOrEnrich(null,'JP|bad|BOX',null),false);
assert.equal(addOrEnrich(null,'JP|bad|BOX',[]),false);
assert.equal(addOrEnrich(null,'JP|bad|BOX',{...good,discovered_market:'true',source_date:'2026-09-24'}),false);
assert.equal(addOrEnrich(null,'JP|bad|BOX|EXTRA',{...good,discovered_market:true}),false);
const before=COUNTRY_BOX_DATA.length;
assert.equal(addRelease({region:'JP',name:'Shared',game:'Digimon',release_date:'2026-09-20'}),true);
assert.equal(COUNTRY_BOX_DATA.length,before+1);
assert.equal(COUNTRY_BOX_DATA.at(-1).game,'Digimon');
assert.equal(addRelease({region:'JP',name:'Shared',game:'ONE PIECE',release_date:'2026-09-21'}),false);
assert.equal(first.release,undefined,'other-game releases are isolated');
assert.equal(second.release,'2026-09-21');
assert.equal(addRelease(null),false);
assert.equal(addRelease({region:'JP',name:'Shared',game:{id:'Pokémon'}}),false);
console.log('V547 PASS: KST day, 14-day boundary, source, score, null and cross-game isolation');
})();
"""
        result = subprocess.run(
            ["node", "-e", implementation + harness],
            cwd=ROOT, capture_output=True, text=True, timeout=15, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("V547 PASS:", result.stdout)


if __name__ == "__main__":
    unittest.main()

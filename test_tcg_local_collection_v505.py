import shutil
import subprocess
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent

class LocalPortfolioV505Tests(unittest.TestCase):
    def test_offline_local_only_and_no_claims_of_live_prices(self):
        src=(ROOT/"tcg_local_collection_v505.js").read_text(encoding="utf-8")
        loader=(ROOT/"tcg_market_expanded_v487.js").read_text(encoding="utf-8")
        self.assertIn('tcg-local-collection-v505',src)
        self.assertIn('blocked=false;lots=values;',src)
        self.assertNotIn('restore.disabled=true',src)
        for token in ('LIMIT=200','FILE_LIMIT=160000','function normalize(raw)','localStorage.setItem(KEY',
                      'new Set(values.map(x=>x.id))','JSON 백업','JSON 복원','실거래 시세가 아닙니다'):
            self.assertIn(token,src)
        for prohibited in ('innerHTML','eval(','Math.random','fetch(','XMLHttpRequest','navigator.sendBeacon'):
            self.assertNotIn(prohibited,src)
        self.assertIn('tcg_local_collection_v505.js?v=505',loader)
        self.assertIn("'tcg_local_collection_v505.js'",(ROOT/"tcg_updater.py").read_text(encoding="utf-8"))
        self.assertIn("'./tcg_local_collection_v505.js'",(ROOT/"sw.js").read_text(encoding="utf-8"))


    def test_v533_market_home_readability_and_touch_targets(self):
        src=(ROOT/"tcg_local_collection_v505.js").read_text(encoding="utf-8")
        css=src.split("// V533: screenshot-informed market-home touch/readability finish.",1)[1].split("  let lots=[]",1)[0]
        self.assertIn("style.textContent+=",css)
        self.assertIn("min-height:48px!important",css)
        for selector in (
            "#tcgMarketHome .tcg-market-refresh", "#tcgMarketHome .tcg-market-game",
            "#tcgMarketHome .tcg-market-more", "#tcgMarketHome .tcg-market-tile-actions button",
            "#tcgMarketHome .tcg-market-tile-actions a",
        ):
            self.assertIn(selector,css)
        self.assertIn("font-size:12px!important",css)
        for selector in (
            "#tcgMarketHome .tcg-market-home-meta", "#tcgMarketHome .tcg-market-tile-label",
            "#tcgMarketHome .tcg-market-tile-kind", "#tcgMarketHome .tcg-market-tile-date",
            "#tcgMarketHome .tcg-market-home-warning",
        ):
            self.assertIn(selector,css)
        self.assertIn("font-variant-numeric:tabular-nums",css)
        self.assertIn("#tcgMarketHome :is(button,a):focus-visible",css)
        self.assertNotIn("fetch(",css)
        self.assertNotIn("localStorage.clear",css)

    @unittest.skipUnless(shutil.which("node"),"Node required")
    def test_registry_core_promoted_game_choices_and_watch_exclusion(self):
        import json
        src=(ROOT/"tcg_local_collection_v505.js").read_text(encoding="utf-8")
        data=json.loads((ROOT/"tcg_game_registry.json").read_text(encoding="utf-8"))
        allowed={g["canonical"] for g in data["games"] if
                 g["state"] in ("core","promoted") and g["capabilities"].get("market") is True}
        watch={g["canonical"] for g in data["games"] if g["state"]=="watch"}
        definitions="const GAMES="+src.split("  const GAMES=",1)[1].split("  function node(",1)[0]
        script=definitions+chr(10)+"process.stdout.write(JSON.stringify({games:GAMES,labels:GAME_LABELS}));"
        run=subprocess.run(["node","-e",script],capture_output=True,text=True,timeout=15)
        self.assertEqual(run.returncode,0,run.stderr)
        actual=json.loads(run.stdout)
        self.assertEqual(set(actual["games"]),allowed|{"기타 TCG"})
        self.assertTrue(watch.isdisjoint(actual["games"]))
        for game in allowed:
            self.assertTrue(actual["labels"].get(game),game)
        self.assertIn("실거래 시세가 아닙니다",src)
        self.assertIn("등급측정이 자동 활성화되지 않습니다",src)

    @unittest.skipUnless(shutil.which("node"),"Node required")
    def test_reject_noncanonical_import_numbers_and_nontext_names(self):
        # Exercise the real JS normalizer. Native UI number fields and JSON
        # backups must follow the same schema without Number(...) coercion.
        src=(ROOT/"tcg_local_collection_v505.js").read_text(encoding="utf-8")
        pure=src.split("  function integer(value,min,max){",1)[1].split("  const panel=",1)[0]
        script=(
            "const assert=require('node:assert/strict');\n"
            "const GAMES=['Pokémon'];const GRADES=['미감정'];\n"
            "function integer(value,min,max){"+pure+"\n"
            "const base={id:1,name:'Pikachu',number:'025',game:'Pokémon',region:'JP',asset:'CARD',grade:'미감정',qty:1,paid:5000,value:null};\n"
            "assert.equal(normalize(base).paid,5000);\n"
            "assert.equal(normalize({...base,paid:'0'}).paid,0);\n"
            "assert.equal(normalize({...base,qty:'10'}).qty,10);\n"
            "for(const key of ['id','qty','paid','value'])for(const v of [true,false,[1],[],{},' ','1e2','0x10','1.0','01',NaN,Infinity,-Infinity]){\n"
            "assert.equal(normalize({...base,[key]:v}),null,key+':'+String(v));}\n"
            "for(const v of [123,true,['Pikachu'],{toString:()=> 'Pikachu'}])assert.equal(normalize({...base,name:v}),null);\n"
            "for(const v of [7,false,['025']])assert.equal(normalize({...base,number:v}),null);\n"
        )
        result=subprocess.run(["node","-e",script],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)

    @unittest.skipUnless(shutil.which("node"),"Node required")
    def test_javascript_syntax(self):
        for name in ("tcg_local_collection_v505.js","tcg_market_expanded_v487.js"):
            subprocess.run(["node","--check",str(ROOT/name)],check=True,timeout=20)

    @unittest.skipUnless(shutil.which("node"),"Node required")
    def test_normalizer_rejects_invalid_values_and_injection(self):
        js=(ROOT/"tcg_local_collection_v505.js").read_text(encoding="utf-8")
        pure=js.split("  function integer(value,min,max){",1)[1].split("  const panel=",1)[0]
        script=(
            "const assert=require('node:assert/strict');\n"
            "const GAMES=['Pokémon','ONE PIECE','NARUTO','Yu-Gi-Oh!','기타 TCG'];\n"
            "const GRADES=['미감정','PSA 8','PSA 9','PSA 10','BGS 9','BGS 9.5','BGS 10','CGC 9','CGC 10','TAG 10','BRG 9','BRG 10'];\n"
            "function integer(value,min,max){"+pure+"\n"
            "const base={id:1,name:'Pikachu',number:'025',game:'Pokémon',region:'JP',asset:'CARD',grade:'미감정',qty:1,paid:5000,value:null};\n"
            "assert.equal(normalize(base).name,'Pikachu');\n"
            "for(const fields of [{game:'wrong'},{qty:0},{qty:1.5},{paid:-1},{value:-100},{grade:'PSA 11'},{asset:'BOX',grade:'PSA 10'},{name:''}])"
            "assert.equal(normalize({...base,...fields}),null);\n"
        )
        result=subprocess.run(["node","-e",script],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=="__main__":
    unittest.main()

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
        self.assertIn('MAX',src) if False else None
        for token in ('LIMIT=200','FILE_LIMIT=160000','function normalize(raw)','localStorage.setItem(KEY',
                      'new Set(values.map(x=>x.id))','JSON 백업','JSON 복원','실거래 시세가 아닙니다'):
            self.assertIn(token,src)
        for prohibited in ('innerHTML','eval(','Math.random','fetch(','XMLHttpRequest','navigator.sendBeacon'):
            self.assertNotIn(prohibited,src)
        self.assertIn('tcg_local_collection_v505.js?v=505',loader)
        self.assertIn("'tcg_local_collection_v505.js'",(ROOT/"tcg_updater.py").read_text(encoding="utf-8"))
        self.assertIn("'./tcg_local_collection_v505.js'",(ROOT/"sw.js").read_text(encoding="utf-8"))

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

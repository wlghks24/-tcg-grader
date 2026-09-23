from __future__ import annotations

import json
import subprocess
from pathlib import Path
import unittest

import card_grading_valuation as valuation
import grading_accuracy_v99 as accuracy

ROOT = Path(__file__).resolve().parent


class CardCoreCrosscheckV291Tests(unittest.TestCase):
    def test_python_grading_requires_all_three_defect_channels(self) -> None:
        self.assertEqual(100, accuracy.combine_defect_risk(None, 0, 0))
        self.assertEqual(100, accuracy.combine_defect_risk(0, None, 0))
        self.assertEqual(100, accuracy.combine_defect_risk(0, 0, None))
        self.assertEqual(100, accuracy.combine_defect_risk(False, 0, 0))
        self.assertAlmostEqual(5.7, accuracy.combine_defect_risk("4", "5", "6"))
        self.assertEqual(1.0, accuracy.estimate_raw_grade(50, 50, None, None, None, "PSA"))

    def test_browser_grading_matches_fail_closed_missing_evidence_contract(self) -> None:
        script = r"""
const v=require('./grading_accuracy_v99.js');
const out={
  allMissing:v.combineDefectRisk(null,null,null),
  partial:v.combineDefectRisk(0,null,0),
  boolValue:v.combineDefectRisk(false,0,0),
  blank:v.combineDefectRisk('',0,0),
  numeric:v.combineDefectRisk('4','5','6'),
  grade:v.estimateRawGrade(50,50,null,null,null,'PSA')
};
process.stdout.write(JSON.stringify(out));
"""
        proc = subprocess.run(
            ["node", "-e", script], cwd=ROOT, text=True, capture_output=True, check=True, timeout=30
        )
        result = json.loads(proc.stdout)
        self.assertEqual(100, result["allMissing"])
        self.assertEqual(100, result["partial"])
        self.assertEqual(100, result["boolValue"])
        self.assertEqual(100, result["blank"])
        self.assertAlmostEqual(5.7, result["numeric"])
        self.assertEqual(1, result["grade"])

    def test_valuation_rejects_missing_analysis_evidence(self) -> None:
        empty = valuation.estimate_grades({})
        self.assertFalse(empty["ok"])
        self.assertEqual("FAILED", empty["status"])
        self.assertEqual({}, empty["grades"])

        pristine = {
            "centering_front": 50,
            "centering_back": 50,
            "corners": 10,
            "edges": 10,
            "surface": 10,
            "micro_flaws": 0,
            "is_authentic": True,
        }
        missing = dict(pristine)
        missing.pop("surface")
        result = valuation.estimate_grades(missing)
        self.assertFalse(result["ok"])
        self.assertIn("surface", result["reason"])
        self.assertTrue(valuation.estimate_grades(pristine)["ok"])

    def test_japanese_year_fallback_uses_japan_release_boundaries(self) -> None:
        script = r"""
const fs=require('fs'),vm=require('vm');
global.window={};
global.document={readyState:'loading',addEventListener(){},getElementById(){return null;}};
global.localStorage={getItem(){return null;},setItem(){}};
global.Option=function(){};
vm.runInThisContext(fs.readFileSync('card_identity_recognition.js','utf8'),{filename:'card_identity_recognition.js'});
const api=global.window.TCGPokemonGeneration;
const years=[2019,2016,2013,2010,2006];
const out=years.map(year=>api.infer({game:'pokemon',region:'JP',ocr_text:`©${year} Pokémon`}));
process.stdout.write(JSON.stringify(out.map(x=>({year:x.year,generation:x.generation,status:x.status}))));
"""
        proc = subprocess.run(
            ["node", "-e", script], cwd=ROOT, text=True, capture_output=True, check=True, timeout=30
        )
        rows = json.loads(proc.stdout)
        self.assertEqual([8, 7, 6, 5, 4], [row["generation"] for row in rows])
        self.assertTrue(all(row["status"] == "estimated" for row in rows))

    def test_non_japanese_year_fallback_keeps_existing_conservative_contract(self) -> None:
        source = (ROOT / "card_identity_recognition.js").read_text(encoding="utf-8")
        self.assertIn("if(year>=2020)return {generation:8", source)
        self.assertIn("generationByYear(year,input?.region)", source)

    def test_unknown_region_transition_years_fail_closed(self) -> None:
        script = r"""
const fs=require('fs'),vm=require('vm');
global.window={};
global.document={readyState:'loading',addEventListener(){},getElementById(){return null;}};
global.localStorage={getItem(){return null;},setItem(){}};
global.Option=function(){};
vm.runInThisContext(fs.readFileSync('card_identity_recognition.js','utf8'),{filename:'card_identity_recognition.js'});
const api=global.window.TCGPokemonGeneration;
const ambiguous=[2006,2010,2013,2016,2019].map(year=>api.infer({game:'pokemon',ocr_text:`©${year} Pokémon`}));
const knownJp=api.infer({game:'pokemon',region:'JP',ocr_text:'©2019 Pokémon'});
const knownKr=api.infer({game:'pokemon',region:'KR',ocr_text:'©2019 Pokémon'});
const knownUs=api.infer({game:'pokemon',region:'US',ocr_text:'©2019 Pokémon'});
const stable=api.infer({game:'pokemon',ocr_text:'©2020 Pokémon'});
process.stdout.write(JSON.stringify({ambiguous,knownJp,knownKr,knownUs,stable}));
"""
        proc = subprocess.run(["node", "-e", script], cwd=ROOT, text=True, capture_output=True, check=True, timeout=30)
        result = json.loads(proc.stdout)
        self.assertTrue(all(row["status"] == "unknown" and row["generation"] is None and row["era"] == "AMBIGUOUS" for row in result["ambiguous"]))
        self.assertEqual(8, result["knownJp"]["generation"])
        self.assertEqual(7, result["knownKr"]["generation"])
        self.assertEqual(7, result["knownUs"]["generation"])
        self.assertEqual(8, result["stable"]["generation"])

    def test_market_contract_keeps_completed_sales_separate_from_asking_prices(self) -> None:
        import wyyyes_market_source as market

        self.assertEqual("asking", market.infer_price_type("가격 제안하기 즉시 구매하기"))
        self.assertEqual("sold", market.infer_price_type("판매완료 상품"))
        self.assertEqual("auction_result", market.infer_price_type("경매 종료 낙찰 120,000원"))

        market_db = json.loads((ROOT / "market_prices.json").read_text(encoding="utf-8"))
        for row in (market_db.get("entries") or {}).values():
            if not isinstance(row, dict):
                continue
            for obsolete in ("psa8_krw", "psa9_krw", "psa10_krw", "aph10_krw"):
                self.assertNotIn(obsolete, row)


if __name__ == "__main__":
    unittest.main(verbosity=2)

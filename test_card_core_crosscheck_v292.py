from __future__ import annotations

import json
from pathlib import Path
import subprocess
import unittest

import card_grading_valuation as valuation
import grading_accuracy_v99 as accuracy
import tablet_runtime_manifest
import tcg_updater

ROOT = Path(__file__).resolve().parent


class CardCoreCrosscheckV292Tests(unittest.TestCase):
    def node_json(self, script: str):
        proc = subprocess.run(
            ["node", "-e", script], cwd=ROOT, text=True, capture_output=True,
            check=True, timeout=30,
        )
        return json.loads(proc.stdout)

    def test_psa_probability_distribution_is_grade_aware_normalized_and_fail_closed(self):
        script = r"""
const p=require('./grading_probability_v292.js');
const common={front:50,back:50,surfaceRisk:0,edgeRisk:0,cornerRisk:0};
const rows={
  missing:p.estimate({psaGrade:10,analysisConfidence:100}),
  g10hi:p.estimate({...common,psaGrade:10,analysisConfidence:100}),
  g10lo:p.estimate({...common,psaGrade:10,analysisConfidence:40}),
  g9:p.estimate({...common,psaGrade:9,analysisConfidence:100}),
  g8:p.estimate({...common,psaGrade:8,analysisConfidence:100})
};
process.stdout.write(JSON.stringify(rows));
"""
        rows = self.node_json(script)
        self.assertEqual("insufficient_evidence", rows["missing"]["status"])
        self.assertEqual({"8": 0, "9": 0, "10": 0}, rows["missing"]["exact"])
        self.assertEqual(100, rows["missing"]["below8"])
        for key in ("g10hi", "g10lo", "g9", "g8"):
            row = rows[key]
            total = row["exact"]["8"] + row["exact"]["9"] + row["exact"]["10"] + row["below8"]
            self.assertAlmostEqual(100.0, total, places=6)
            self.assertTrue(all(0 <= row["exact"][str(grade)] <= 100 for grade in (8, 9, 10)))
            self.assertEqual("heuristic_uncertainty_not_empirically_calibrated", row["model"])
        self.assertGreater(rows["g10hi"]["exact"]["10"], rows["g9"]["exact"]["10"])
        self.assertGreater(rows["g9"]["exact"]["9"], rows["g9"]["exact"]["10"])
        self.assertGreater(rows["g8"]["exact"]["8"], rows["g8"]["exact"]["9"])
        self.assertGreater(rows["g10hi"]["exact"]["10"], rows["g10lo"]["exact"]["10"])

    def test_probability_runtime_is_wired_without_cumulative_9_fallback(self):
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        shell = (ROOT / "ui_app_shell_v272.js").read_text(encoding="utf-8")
        self.assertIn('grading_probability_v292.js?v=292', page)
        self.assertIn('TCGGradeProbabilityV292.estimate', page)
        self.assertIn('window.tcgGradeProbabilityMeta', page)
        self.assertIn('PSA 예상확률(휴리스틱)', shell)
        self.assertNotIn('grade === 9 ? "p9prob"', shell)

    def test_every_positive_static_grade_price_has_structured_evidence(self):
        db = json.loads((ROOT / "market_prices.json").read_text(encoding="utf-8"))
        allowed = {"sold", "auction_result", "official_example", "market_guide"}
        for market_key, profile in (db.get("graded_prices") or {}).items():
            if not isinstance(profile, dict):
                continue
            evidence = profile.get("grade_price_evidence") or {}
            for company, grades in (profile.get("grade_prices_krw") or {}).items():
                if not isinstance(grades, dict):
                    continue
                for grade, price in grades.items():
                    if float(price or 0) <= 0:
                        continue
                    row = ((evidence.get(company) or {}).get(str(grade)) or {})
                    self.assertTrue(str(row.get("source") or "").startswith("https://"), (market_key, company, grade))
                    self.assertIn(row.get("price_type"), allowed, (market_key, company, grade))
                    self.assertTrue(row.get("observed_on") or row.get("observed_period"), (market_key, company, grade))

    def test_valuation_carries_exact_grade_evidence_without_price_fabrication(self):
        pristine = {
            "centering_front": 50, "centering_back": 50, "corners": 10,
            "edges": 10, "surface": 10, "micro_flaws": 0, "is_authentic": True,
        }
        evidence = {"PSA": {"10": {
            "source": "https://example.com/sold/1", "price_type": "sold",
            "observed_on": "2026-09-22", "label": "exact sold example",
        }}}
        result = valuation.verified_card_valuation(
            "Test", pristine, {"PSA": {"10": 123456}},
            grade_price_evidence=evidence,
        )
        self.assertEqual(123456, result["valuations"]["PSA"]["krw"])
        self.assertTrue(result["valuations"]["PSA"]["evidence_verified"])
        self.assertEqual("sold", result["valuations"]["PSA"]["evidence"]["price_type"])
        self.assertIsNone(result["valuations"]["BGS"]["krw"])

    def test_generation_boundaries_and_stronger_evidence_precedence(self):
        script = r"""
const fs=require('fs'),vm=require('vm');
global.window={};
global.document={readyState:'loading',addEventListener(){},getElementById(){return null;}};
global.localStorage={getItem(){return null;},setItem(){}};
global.Option=function(){};
vm.runInThisContext(fs.readFileSync('card_identity_recognition.js','utf8'),{filename:'card_identity_recognition.js'});
const api=global.window.TCGPokemonGeneration;
const out={
 jp:[2019,2016,2013,2010,2006].map(year=>api.infer({game:'pokemon',region:'JP',ocr_text:`©${year}`})),
 kr:[2020,2017,2014,2011,2007].map(year=>api.infer({game:'pokemon',region:'KR',ocr_text:`©${year}`})),
 us:[2020,2017,2014,2011,2007].map(year=>api.infer({game:'pokemon',region:'US',ocr_text:`©${year}`})),
 precedence:api.infer({game:'pokemon',region:'JP',card_number:'SV8A217',ocr_text:'©2010'})
};
process.stdout.write(JSON.stringify(out));
"""
        out = self.node_json(script)
        self.assertEqual([8, 7, 6, 5, 4], [row["generation"] for row in out["jp"]])
        self.assertEqual([8, 7, 6, 5, 4], [row["generation"] for row in out["kr"]])
        self.assertEqual([8, 7, 6, 5, 4], [row["generation"] for row in out["us"]])
        self.assertEqual(9, out["precedence"]["generation"])
        self.assertEqual("SV8A", out["precedence"]["expansion_code"])

    def test_learning_remains_downward_only_and_missing_grading_evidence_fails_closed(self):
        for company in accuracy.COMPANIES:
            for raw in (5, 8, 9, 10):
                corrected = accuracy.apply_downward_correction(company, raw, -1)
                self.assertLessEqual(corrected, raw)
        self.assertEqual(1.0, accuracy.estimate_raw_grade(50, 50, None, 0, 0, "PSA"))
        self.assertEqual(1.0, accuracy.estimate_raw_grade(50, 50, 0, None, 0, "BGS"))

    def test_probability_asset_is_in_tablet_server_and_pwa_runtime(self):
        for dependency in (
            "grading_accuracy_v99.py", "card_grading_valuation.py", "card_identity_recognition.py", "server_security_guard.py",
            "grading_vision_engine.js", "grading_accuracy_v99.js", "grading_probability_v292.js", "card_identity_recognition.js",
        ):
            self.assertIn(dependency, tablet_runtime_manifest.ACTIVE_RUNTIME_FILES)
        self.assertIn("grading_probability_v292.js", tcg_updater.PUBLIC_STATIC_FILES)
        worker = (ROOT / "sw.js").read_text(encoding="utf-8")
        self.assertIn("./grading_probability_v292.js", worker)
        self.assertIn("tcg-v292-card-core-runtime", worker)


if __name__ == "__main__":
    unittest.main(verbosity=2)

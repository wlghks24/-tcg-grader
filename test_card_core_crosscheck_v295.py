from __future__ import annotations

import json
import subprocess
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


class CardCoreCrosscheckV295Tests(unittest.TestCase):
    def test_psa_probability_distribution_is_normalized_and_monotonic(self) -> None:
        script = r"""
const v=require('./grading_accuracy_v99.js');
const vectors=[[98,97],[97,98],[120,110],[-5,20],[70,85],[0,0],[20,10],[null,80]];
const rows=vectors.map(([p10,p9])=>v.normalizePsaProbabilities(p10,p9));
process.stdout.write(JSON.stringify(rows));
"""
        proc = subprocess.run(
            ["node", "-e", script], cwd=ROOT, text=True, capture_output=True, check=True, timeout=30
        )
        rows = json.loads(proc.stdout)
        for row in rows:
            total = row["8"] + row["9"] + row["10"] + row["below"]
            self.assertAlmostEqual(100.0, total, places=8)
            for key in ("8", "9", "10", "below", "psa9plus"):
                self.assertGreaterEqual(row[key], 0)
                self.assertLessEqual(row[key], 100)
            self.assertGreaterEqual(row["psa9plus"], row["10"])
            self.assertAlmostEqual(row["psa9plus"], row["9"] + row["10"], places=8)

    def test_index_uses_shared_probability_normalizer(self) -> None:
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("normalizePsaProbabilities(p10,p9)", page)
        self.assertIn("p9=psaDist.psa9plus", page)
        self.assertIn("window.tcgGradeProbabilities={8:p8,9:p9only,10:p10,below}", page)
        self.assertNotIn("Math.max(1,p9-p10)", page)

    def test_explicit_market_edition_mismatch_fails_closed(self) -> None:
        source = (ROOT / "grade_market_flow.js").read_text(encoding="utf-8")
        self.assertIn("const wanted=editionCode(region),actual=editionCode(row.card_region||'UNKNOWN')", source)
        self.assertIn("actual!==wanted)return -999", source)
        self.assertNotIn("actual!==wanted)score-=40", source)

    def test_v291_v292_safety_contracts_remain_present(self) -> None:
        accuracy = (ROOT / "grading_accuracy_v99.js").read_text(encoding="utf-8")
        identity = (ROOT / "card_identity_recognition.js").read_text(encoding="utf-8")
        valuation = (ROOT / "card_grading_valuation.py").read_text(encoding="utf-8")
        self.assertIn("if(!inputs.every(([value])=>finite(value)))return 100", accuracy)
        self.assertIn("generationByYear(year,input?.region)", identity)
        self.assertIn("for(const match of t.matchAll(/(?:©|\\(C\\)|COPYRIGHT\\s*)", identity)
        self.assertIn("identityRegion')?.addEventListener('change',refreshGenerationFromInputs", identity)
        self.assertIn("카드 분석자료 부족", valuation)


if __name__ == "__main__":
    unittest.main(verbosity=2)

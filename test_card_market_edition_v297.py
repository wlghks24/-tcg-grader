from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


class CardMarketEditionV297Tests(unittest.TestCase):
    def test_known_card_region_rejects_unknown_quote_region(self) -> None:
        source = (ROOT / "grade_market_flow.js").read_text(encoding="utf-8")
        self.assertIn(
            "const wanted=editionCode(region),actual=editionCode(row.card_region||'UNKNOWN')",
            source,
        )
        self.assertIn(
            "if(wanted!=='UNKNOWN'&&actual===wanted)score+=20;",
            source,
        )
        self.assertIn(
            "else if(wanted!=='UNKNOWN'&&actual!==wanted)return -999;",
            source,
        )
        self.assertNotIn(
            "actual!=='UNKNOWN'&&actual!==wanted",
            source,
        )

    def test_unknown_user_region_still_allows_reference_discovery(self) -> None:
        source = (ROOT / "grade_market_flow.js").read_text(encoding="utf-8")
        # The strict rejection remains gated by a known requested edition.
        self.assertIn("wanted!=='UNKNOWN'&&actual!==wanted", source)
        self.assertNotIn("if(actual==='UNKNOWN')return -999", source)

    def test_v291_v295_v296_card_core_contracts_remain_present(self) -> None:
        accuracy = (ROOT / "grading_accuracy_v99.js").read_text(encoding="utf-8")
        valuation = (ROOT / "card_grading_valuation.py").read_text(encoding="utf-8")
        identity = (ROOT / "card_identity_recognition.js").read_text(encoding="utf-8")
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("if(!inputs.every(([value])=>finite(value)))return 100", accuracy)
        self.assertIn("normalizePsaProbabilities", accuracy)
        self.assertIn("카드 분석자료 부족", valuation)
        self.assertIn("generationByYear(year,input?.region)", identity)
        self.assertIn("window.tcgGradeProbabilities={8:p8,9:p9only,10:p10,below}", page)


if __name__ == "__main__":
    unittest.main(verbosity=2)

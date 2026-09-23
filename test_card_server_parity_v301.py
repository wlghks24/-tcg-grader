from __future__ import annotations

import unittest

import card_grading_valuation as valuation
import grading_accuracy_v99 as accuracy


class CardServerParityV301Tests(unittest.TestCase):
    @staticmethod
    def payload(
        *,
        centering_front: float = 50,
        centering_back: float = 50,
        corners: float = 10,
        edges: float = 10,
        surface: float = 10,
        micro_flaws: int = 0,
    ) -> dict[str, object]:
        return {
            "centering_front": centering_front,
            "centering_back": centering_back,
            "corners": corners,
            "edges": edges,
            "surface": surface,
            "micro_flaws": micro_flaws,
            "is_authentic": True,
        }

    @staticmethod
    def score_to_risk(score: float) -> float:
        score = max(1.0, min(10.0, float(score)))
        if score <= 1.0:
            return 100.0
        return max(0.0, min(100.0, (10.0 - score) / 0.09))

    def canonical_expected(self, values: dict[str, object]) -> dict[str, float]:
        front_larger = max(float(values["centering_front"]), 100.0 - float(values["centering_front"]))
        back_larger = max(float(values["centering_back"]), 100.0 - float(values["centering_back"]))
        front = max(0.0, min(50.0, 100.0 - front_larger))
        back = max(0.0, min(50.0, 100.0 - back_larger))
        surface_risk = self.score_to_risk(float(values["surface"]))
        edge_risk = self.score_to_risk(float(values["edges"]))
        corner_risk = self.score_to_risk(float(values["corners"]))
        return {
            company: accuracy.estimate_raw_grade(
                front, back, surface_risk, edge_risk, corner_risk, company
            )
            for company in valuation.COMPANIES
        }

    def test_server_uses_same_canonical_v99_core_for_browser_snapshot_scores(self) -> None:
        vectors = [
            self.payload(),
            self.payload(centering_front=60, centering_back=60),
            self.payload(centering_front=55, centering_back=75),
            self.payload(edges=8),
            self.payload(corners=7.5, surface=8.5),
        ]
        for values in vectors:
            with self.subTest(values=values):
                result = valuation.estimate_grades(values)
                self.assertTrue(result["ok"])
                self.assertEqual(self.canonical_expected(values), result["grades"])
                self.assertEqual("v99-canonical-server", result.get("grading_engine"))
                self.assertFalse(result["official_grade"])

    def test_known_previous_divergence_60_40_is_psa_9_not_psa_8(self) -> None:
        values = self.payload(centering_front=60, centering_back=60)
        result = valuation.estimate_grades(values)
        self.assertEqual(9.0, result["grades"]["PSA"])
        self.assertEqual(
            accuracy.estimate_raw_grade(40, 40, 0, 0, 0, "PSA"),
            result["grades"]["PSA"],
        )

    def test_micro_flaw_remains_conservative_and_cannot_return_pristine_psa_10(self) -> None:
        result = valuation.estimate_grades(self.payload(micro_flaws=1))
        self.assertTrue(result["ok"])
        self.assertLess(result["grades"]["PSA"], 10.0)
        self.assertGreaterEqual(result["components"]["surface_risk"], 5.5)

    def test_fail_closed_contract_is_unchanged(self) -> None:
        values = self.payload()
        values.pop("surface")
        result = valuation.estimate_grades(values)
        self.assertFalse(result["ok"])
        self.assertEqual("FAILED", result["status"])
        self.assertIn("surface", result["reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

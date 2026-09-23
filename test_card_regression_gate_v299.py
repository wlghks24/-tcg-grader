from __future__ import annotations

import shutil
import unittest
from pathlib import Path

import verify_current_runtime as runtime

ROOT = Path(__file__).resolve().parent


class CardRegressionGateV299Tests(unittest.TestCase):
    def test_static_card_regressions_are_always_in_current_runtime(self) -> None:
        commands = {name: cmd for name, cmd, _timeout, _optional in runtime._commands()}
        self.assertIn("card_core_static_regressions", commands)
        command = commands["card_core_static_regressions"]
        for test_name in (
            "test_card_core_provenance_v296.py",
            "test_card_market_edition_v297.py",
            "test_card_probability_ui_v298.py",
            "test_card_regression_gate_v299.py",
        ):
            self.assertIn(test_name, command)

    def test_node_card_regressions_are_wired_without_forcing_node_on_tablet(self) -> None:
        source = (ROOT / "verify_current_runtime.py").read_text(encoding="utf-8")
        for test_name in (
            "test_card_core_crosscheck_v292.py",
            "test_card_core_crosscheck_v295.py",
            "test_pokemon_generation_display_v207.py",
        ):
            self.assertIn(test_name, source)
        self.assertIn('if shutil.which("node"):', source)
        commands = {name: cmd for name, cmd, _timeout, _optional in runtime._commands()}
        if shutil.which("node"):
            self.assertIn("card_core_node_regressions", commands)
        else:
            self.assertNotIn("card_core_node_regressions", commands)

    def test_card_safety_contracts_remain_fail_closed(self) -> None:
        accuracy = (ROOT / "grading_accuracy_v99.js").read_text(encoding="utf-8")
        identity = (ROOT / "card_identity_recognition.js").read_text(encoding="utf-8")
        market = (ROOT / "grade_market_flow.js").read_text(encoding="utf-8")
        shell = (ROOT / "ui_app_shell_v272.js").read_text(encoding="utf-8")
        updater = (ROOT / "tcg_updater.py").read_text(encoding="utf-8")

        self.assertIn("if(!inputs.every(([value])=>finite(value)))return 100", accuracy)
        self.assertIn("normalizePsaProbabilities", accuracy)
        self.assertIn("generationByYear(year,input?.region)", identity)
        self.assertIn("COPYRIGHT\\s*", identity)
        self.assertIn("else if(wanted!=='UNKNOWN'&&actual!==wanted)return -999;", market)
        self.assertIn("window.tcgGradeProbabilities", shell)
        self.assertNotIn('grade === 9 ? "p9prob"', shell)
        self.assertIn("grade_price_evidence=profile.get('grade_price_evidence',{}) if profile else None", updater)
        self.assertIn("price_source='exact_company_grade_observation' if profile else 'user_provided_exact_grade'", updater)

    def test_runtime_delivery_workflow_tracks_card_core_regressions(self) -> None:
        workflow = (ROOT / ".github/workflows/runtime-delivery-guard.yml").read_text(encoding="utf-8")
        for token in (
            "card_grading_valuation.py",
            "grading_accuracy_v99.py",
            "grading_accuracy_v99.js",
            "grade_market_flow.js",
            "ui_app_shell_v272.js",
            "test_card_core_crosscheck_v292.py",
            "test_card_core_crosscheck_v295.py",
            "test_card_core_provenance_v296.py",
            "test_card_market_edition_v297.py",
            "test_card_probability_ui_v298.py",
            "test_card_regression_gate_v299.py",
            "test_pokemon_generation_display_v207.py",
        ):
            self.assertIn(token, workflow)
        self.assertIn("python -m unittest -v test_card_core_provenance_v296.py", workflow)
        self.assertIn("python -m unittest -v test_card_core_crosscheck_v292.py", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)

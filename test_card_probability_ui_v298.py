from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHELL = ROOT / "ui_app_shell_v272.js"


class CardProbabilityUIV298Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SHELL.read_text(encoding="utf-8")

    def _probability_function(self) -> str:
        match = re.search(
            r"function probabilityText\(grade\)\s*\{(?P<body>.*?)\n  \}\n\n  function generationText",
            self.source,
            flags=re.S,
        )
        self.assertIsNotNone(match, "probabilityText function must remain discoverable")
        return match.group("body")

    def test_exact_psa9_never_reuses_legacy_psa9plus_dom_value(self) -> None:
        body = self._probability_function()
        self.assertNotIn('nodeText("p9prob")', body)
        self.assertNotIn('grade === 9 ? "p9prob"', body)
        self.assertIn("window.tcgGradeProbabilities", body)

    def test_psa10_may_use_equivalent_exact_fallback_only(self) -> None:
        body = self._probability_function()
        self.assertIn('if (grade === 10)', body)
        self.assertIn('nodeText("p10prob")', body)
        self.assertIn('return "-"', body)

    def test_shell_marks_probability_semantics_revision(self) -> None:
        self.assertIn('const VERSION = "v298-exact-psa9-probability"', self.source)


if __name__ == "__main__":
    unittest.main(verbosity=2)

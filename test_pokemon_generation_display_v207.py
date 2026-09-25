#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class PokemonGenerationDisplayV207Tests(unittest.TestCase):
    def test_pregrade_result_has_generation_ui_and_versioned_identity_runtime(self):
        page = (ROOT / "index.html").read_text(encoding="utf-8")
        for token in (
            'id="simplePokemonGeneration"',
            'id="pokemonGenerationBadge"',
            'id="pokemonGenerationTitle"',
            'id="pokemonGenerationMeta"',
            "세대 판별 중",
            "card_identity_recognition.js?v=207",
            "TCGPokemonGeneration?.render",
        ):
            self.assertIn(token, page)

    def test_identity_runtime_keeps_evidence_priority_and_fail_closed_policy(self):
        source = (ROOT / "card_identity_recognition.js").read_text(encoding="utf-8")
        for token in (
            "expansionFromCardNumber",
            "generationBySetCode",
            "generationByRegulation",
            "generationByYear",
            "confidence_level:'high'",
            "confidence_level:'context'",
            "confidence_level:'low'",
            "status:'context_only'",
            "status:'unknown'",
            "세대 근거가 부족해 번호를 생성하지 않았습니다.",
            "EN_SV_CODES",
            "EN_MEGA_CODES",
            "inferEditionFromText",
            "identityCoreKey",
            "generationConflict",
            "edition_evidence_conflict",
            "v315-evidence-isolated-confirmed-learning",
            "같은 사진에 서로 다른 카드/판본 정보",
        ):
            self.assertIn(token, source)
        self.assertIn("confidence:evidence_count>=2?.995:.98", source)
        self.assertIn("confidence:.50", source)
        self.assertIn("레귤레이션 마크는 대회 사용 가능성 표기", source)
        self.assertIn("version:'v320'", source)

    def test_generation_runtime_executes(self):
        result = subprocess.run(
            ["node", str(ROOT / "verify_pokemon_generation_runtime.js")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("Pokémon generation runtime v320: PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()

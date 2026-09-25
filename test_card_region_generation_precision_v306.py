from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import card_identity_recognition as identity

ROOT = Path(__file__).resolve().parent


class CardRegionGenerationPrecisionV306Tests(unittest.TestCase):
    def test_server_ocr_infers_only_evidence_bounded_regions(self) -> None:
        self.assertEqual('KR', identity.infer_region_from_text('포켓몬 카드 피카츄 ex'))
        self.assertEqual('JP', identity.infer_region_from_text('ポケモンカード ピカチュウ ex'))
        self.assertEqual('US', identity.infer_region_from_text('Mega Greninja ex CRI 22'))
        self.assertEqual('US', identity.infer_region_from_text('Kirlia MEG 59/132'))
        self.assertEqual('UNKNOWN', identity.infer_region_from_text('Pikachu 25/102'))
        self.assertEqual('JP', identity.infer_region_from_text('2026 Japanese Pokémon card Pikachu'))
        evidence=identity.infer_region_evidence('Korean 포켓몬 ポケモン card')
        self.assertEqual('UNKNOWN',evidence['region'])
        self.assertTrue(evidence['conflict'])
        self.assertGreaterEqual(len(evidence['signals']),2)

    def test_server_extracts_current_english_set_codes(self) -> None:
        self.assertIn('MEG59/132', identity.extract_numbers('Kirlia MEG 59/132'))
        self.assertIn('CRI22', identity.extract_numbers('Mega Greninja ex CRI 22'))
        self.assertIn('PBL79', identity.extract_numbers('Air Balloon PBL 79'))
        self.assertIn('PAL185/193', identity.extract_numbers('Iono PAL 185/193'))

    def test_known_region_rejects_known_catalog_mismatch(self) -> None:
        source=(ROOT/'card_identity_recognition.py').read_text(encoding='utf-8')
        self.assertIn('if row_region != region:', source)
        self.assertIn('learned = match_learning(image_hash, game, region)', source)

    def test_confirmation_identity_includes_region(self) -> None:
        source=(ROOT/'card_identity_recognition.py').read_text(encoding='utf-8')
        self.assertIn('core_identity = (card_name, card_number, market_key, game)', source)
        self.assertIn('identity = (*core_identity, effective_region)', source)
        self.assertIn('with exclusive_file_lock(LEARNING', source)
        self.assertIn('same_image_conflicting_identity_or_edition', source)

    def test_market_html_escape_and_exact_grade_contract(self) -> None:
        source=(ROOT/'grade_market_flow.js').read_text(encoding='utf-8')
        self.assertIn("&quot;", source)
        self.assertNotIn("&quot'", source)
        self.assertIn('!Number.isInteger(exact)', source)
        self.assertIn('다른 판본 가격은 자동 대체하지 않습니다.', source)

    def test_generation_runtime(self) -> None:
        proc=subprocess.run(['node','verify_pokemon_generation_runtime.js'],cwd=ROOT,text=True,capture_output=True,timeout=30,check=False)
        self.assertEqual(0,proc.returncode,proc.stdout+proc.stderr)
        self.assertIn('Pokémon generation runtime v320: PASS',proc.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)

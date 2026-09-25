from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class CardEditionPrecisionV302Tests(unittest.TestCase):
    def _browser_identity(self, mode: str, payload: dict) -> dict:
        script = r"""
const fs=require('fs'),vm=require('vm');
global.window={};
global.document={readyState:'loading',addEventListener(){},getElementById(){return null;}};
global.localStorage={getItem(){return null;},setItem(){}};
global.Option=function(){};
vm.runInThisContext(fs.readFileSync('card_identity_recognition.js','utf8'));
const mode=process.argv[1], input=JSON.parse(process.argv[2]);
const out=mode==='region'
  ? global.window.TCGPokemonGeneration.inferRegion(input.text||'')
  : global.window.TCGPokemonGeneration.infer(input);
process.stdout.write(JSON.stringify(out));
"""
        proc = subprocess.run(
            ["node", "-e", script, mode, json.dumps(payload, ensure_ascii=False)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=20,
            check=True,
        )
        return json.loads(proc.stdout)

    def test_identity_tracks_modern_english_sets_and_safe_region_evidence(self) -> None:
        source = (ROOT / "card_identity_recognition.js").read_text(encoding="utf-8")
        for token in (
            "EN_SV_CODES",
            "'PAL'",
            "'OBF'",
            "'TWM'",
            "'SSP'",
            "EN_MEGA_CODES",
            "'MEG'",
            "'PFL'",
            "'ASC'",
            "'POR'",
            "inferEditionFromText",
            "hangul_script",
            "kana_script",
            "english_set_code_",
            "insufficient_evidence",
        ):
            self.assertIn(token, source)
        self.assertIn("MEGA는 별도 TCG 시리즈/블록", source)
        self.assertIn("레귤레이션 마크는 대회 사용 가능성 표기", source)
        if shutil.which("node"):
            result = self._browser_identity("generation", {"game": "pokemon", "regulation_mark": "G"})
            self.assertEqual("estimated", result["status"])
            self.assertEqual(9, result["generation"])
            self.assertEqual("medium", result["confidence_level"])
            self.assertAlmostEqual(0.72, float(result["confidence"]), places=6)

    def test_unknown_region_can_retry_ocr_with_evidence_bounded_edition(self) -> None:
        source = (ROOT / "card_identity_recognition.js").read_text(encoding="utf-8")
        self.assertIn("requestRegion=selected!=='UNKNOWN'?selected:browserRegion.region", source)
        self.assertIn("selected==='UNKNOWN'&&requestRegion==='UNKNOWN'&&effectiveRegion!=='UNKNOWN'", source)
        self.assertIn("const retry=await request(effectiveRegion)", source)
        self.assertIn("edition_evidence_conflict", source)
        if shutil.which("node"):
            cases = (
                ("포켓몬 카드 피카츄", "KR", False),
                ("ポケモンカード ピカチュウ", "JP", False),
                ("PAL 001/193", "US", False),
                ("포켓몬 카드 ポケモン カード", "UNKNOWN", True),
            )
            for text, expected_region, expected_conflict in cases:
                with self.subTest(text=text):
                    result = self._browser_identity("region", {"text": text})
                    self.assertEqual(expected_region, result["region"])
                    self.assertEqual(expected_conflict, bool(result.get("conflict", False)))

    def test_local_identity_learning_is_edition_aware(self) -> None:
        source = (ROOT / "card_identity_recognition.js").read_text(encoding="utf-8")
        self.assertIn("identityCoreKey", source)
        self.assertIn("normalizeRegion(item.region)", source)
        self.assertIn("oldRegion!=='UNKNOWN'&&targetRegion!=='UNKNOWN'&&oldRegion!==targetRegion", source)
        self.assertIn("oldRegion==='UNKNOWN'&&targetRegion!=='UNKNOWN'", source)
        self.assertIn("같은 사진에 서로 다른 카드/판본 정보", source)
        self.assertIn("동일 판본 유사 사진 재인식 활성화", source)

    def test_market_saved_profile_lookup_fails_closed_by_edition(self) -> None:
        market = (ROOT / "grade_market_flow.js").read_text(encoding="utf-8")
        for token in (
            "function marketKeyEdition",
            "function editionSearchToken",
            "function findMarketKey(name,number,region)",
            "wanted==='UNKNOWN'||marketKeyEdition(direct)===wanted",
            "if(wanted!=='UNKNOWN'&&actual!==wanted)continue",
            "ranked[0].score===ranked[1].score",
            "findMarketKey(name,number,region)",
            "다른 판본 가격은 자동 대체하지 않습니다.",
        ):
            self.assertIn(token, market)
        self.assertIn("editionSearchToken(editionCode(region))", market)

    def test_half_grade_price_guard_is_preserved(self) -> None:
        market = (ROOT / "grade_market_flow.js").read_text(encoding="utf-8")
        self.assertIn("!Number.isInteger(exact)", market)
        self.assertIn("const sale=gradeSale(c,g)", market)
        self.assertIn("정확 등급 거래자료 없음", market)
        self.assertNotIn("Math.floor(Number(grade))", market)

    @unittest.skipUnless(shutil.which("node"), "Node.js is optional on tablet runtime")
    def test_generation_and_region_runtime_executes(self) -> None:
        result = subprocess.run(
            ["node", str(ROOT / "verify_pokemon_generation_runtime.js")],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        match = re.search(r"Pokémon generation runtime v(\d+): PASS", result.stdout)
        self.assertIsNotNone(match, result.stdout)
        self.assertGreaterEqual(int(match.group(1)), 309)


if __name__ == "__main__":
    unittest.main(verbosity=2)

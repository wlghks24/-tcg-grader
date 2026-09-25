from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

import card_identity_recognition as identity

ROOT = Path(__file__).resolve().parent


class CardRegionLabelAliasV319Tests(unittest.TestCase):
    def test_server_region_aliases_normalize_to_canonical_editions(self) -> None:
        expected = {
            "KR": "KR", "KOR": "KR", "한국판": "KR", "한글판": "KR", "한판": "KR",
            "JP": "JP", "JPN": "JP", "日本版": "JP", "일본판": "JP", "일판": "JP",
            "US": "US", "EN": "US", "ENG": "US", "ENGLISH": "US", "영문판": "US", "영판": "US",
        }
        for raw, canonical in expected.items():
            with self.subTest(raw=raw):
                self.assertEqual(canonical, identity.normalize_region(raw))

    def test_explicit_korean_collector_labels_do_not_self_conflict(self) -> None:
        samples = {
            "한국판 피카츄": "KR",
            "한판 Pikachu": "KR",
            "일본판 피카츄": "JP",
            "일판 Pikachu": "JP",
            "영문판 피카츄": "US",
            "영판 Pikachu": "US",
        }
        for text, expected in samples.items():
            with self.subTest(text=text):
                evidence = identity.infer_region_evidence(text)
                self.assertEqual(expected, evidence["region"])
                self.assertFalse(evidence["conflict"])
                self.assertIn("explicit_region_label", evidence["basis"])

    def test_independent_set_code_still_conflicts_with_wrong_explicit_edition(self) -> None:
        evidence = identity.infer_region_evidence("일본판 Pikachu PAL185/193")
        self.assertEqual("UNKNOWN", evidence["region"])
        self.assertTrue(evidence["conflict"])
        self.assertEqual({"JP", "US"}, {row["region"] for row in evidence["signals"]})

    def _browser(self, text: str) -> dict:
        script = r'''
const fs=require('fs'),vm=require('vm');
global.window={};
global.document={readyState:'loading',addEventListener(){},getElementById(){return null;}};
global.localStorage={getItem(){return null;},setItem(){}};
global.Option=function(){};
vm.runInThisContext(fs.readFileSync('card_identity_recognition.js','utf8'));
process.stdout.write(JSON.stringify(global.window.TCGPokemonGeneration.inferRegion(process.argv[1])));
'''
        proc = subprocess.run(
            ["node", "-e", script, text], cwd=ROOT, text=True, capture_output=True,
            timeout=30, check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        return json.loads(proc.stdout)

    def test_browser_matches_server_for_collector_labels(self) -> None:
        for text, expected in (
            ("일본판 피카츄", "JP"), ("일판 Pikachu", "JP"),
            ("영문판 피카츄", "US"), ("영판 Pikachu", "US"),
            ("한판 Pikachu", "KR"),
        ):
            with self.subTest(text=text):
                row = self._browser(text)
                self.assertEqual(expected, row["region"])
                self.assertFalse(row["conflict"])

    def test_browser_keeps_real_cross_edition_conflict_fail_closed(self) -> None:
        row = self._browser("일본판 Pikachu PAL185/193")
        self.assertEqual("UNKNOWN", row["region"])
        self.assertTrue(row["conflict"])

    def test_pwa_cache_is_rotated_for_identity_runtime_change(self) -> None:
        sw = (ROOT / "sw.js").read_text(encoding="utf-8")
        self.assertIn("const CACHE='tcg-v319-network-first-runtime'", sw)
        self.assertIn("'./card_identity_recognition.js'", sw)


if __name__ == "__main__":
    unittest.main(verbosity=2)

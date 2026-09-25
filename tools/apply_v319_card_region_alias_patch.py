#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 match, found {count}")
    return text.replace(old, new, 1)


# Server: normalize common collector-facing edition aliases and avoid treating the
# Hangul inside an explicit edition descriptor as contradictory card-script evidence.
path = "card_identity_recognition.py"
src = read(path)
src = replace_once(
    src,
    '''def normalize_region(value: Any) -> str:\n    region = str(value or "").strip().upper()\n    return region if region in REGIONS else "UNKNOWN"\n''',
    '''def normalize_region(value: Any) -> str:\n    region = unicodedata.normalize("NFKC", str(value or "")).strip().upper().replace(" ", "")\n    aliases = {\n        "KR": "KR", "KOR": "KR", "KOREA": "KR", "KOREAN": "KR",\n        "한국": "KR", "한국판": "KR", "한글판": "KR", "한판": "KR", "국판": "KR",\n        "JP": "JP", "JPN": "JP", "JAPAN": "JP", "JAPANESE": "JP",\n        "日本": "JP", "日本版": "JP", "日版": "JP", "일본판": "JP", "일판": "JP",\n        "US": "US", "USA": "US", "EN": "US", "ENG": "US", "ENGLISH": "US",\n        "영문판": "US", "영판": "US", "미국판": "US",\n        "UNKNOWN": "UNKNOWN",\n    }\n    return aliases.get(region, "UNKNOWN")\n''',
    "server normalize_region aliases",
)
src = replace_once(
    src,
    '''    explicit_patterns = (\n        ("KR", r"(?:\\b(?:KR|KOREA|KOREAN)\\b|한국판|한글판|국판)"),\n        ("JP", r"(?:\\b(?:JP|JAPAN|JAPANESE)\\b|日本版|日版)"),\n        ("US", r"(?:\\b(?:US|USA|ENGLISH)\\b|영문판|미국판)"),\n    )\n    for region, pattern in explicit_patterns:\n        if re.search(pattern, upper, re.I):\n            signals.append({"region": region, "basis": "explicit_region_label", "confidence": 0.99})\n\n    hangul = len(re.findall(r"[가-힣]", text))\n    kana = len(re.findall(r"[ぁ-んァ-ヶー]", text))\n    if hangul >= 2:\n        signals.append({"region": "KR", "basis": "hangul_script", "confidence": 0.96, "count": hangul})\n    if kana >= 2:\n        signals.append({"region": "JP", "basis": "kana_script", "confidence": 0.96, "count": kana})\n''',
    '''    explicit_patterns = (\n        ("KR", r"(?:\\b(?:KR|KOR|KOREA|KOREAN)\\b|한국판|한글판|한판|국판)"),\n        ("JP", r"(?:\\b(?:JP|JPN|JAPAN|JAPANESE)\\b|日本版|日版|일본판|일판)"),\n        ("US", r"(?:\\b(?:US|USA|EN|ENG|ENGLISH)\\b|영문판|영판|미국판)"),\n    )\n    explicit_regions = set()\n    for region, pattern in explicit_patterns:\n        if re.search(pattern, upper, re.I):\n            explicit_regions.add(region)\n            signals.append({"region": region, "basis": "explicit_region_label", "confidence": 0.99})\n\n    # Explicit collector-facing labels ("일판", "영문판", etc.) are metadata,\n    # not text printed on the card.  Once one is present, do not let the Hangul\n    # inside the descriptor itself create a fake KR conflict.  Independent set\n    # code evidence is still evaluated below and can correctly conflict.\n    if not explicit_regions:\n        hangul = len(re.findall(r"[가-힣]", text))\n        kana = len(re.findall(r"[ぁ-んァ-ヶー]", text))\n        if hangul >= 2:\n            signals.append({"region": "KR", "basis": "hangul_script", "confidence": 0.96, "count": hangul})\n        if kana >= 2:\n            signals.append({"region": "JP", "basis": "kana_script", "confidence": 0.96, "count": kana})\n''',
    "server explicit label precedence",
)
write(path, src)


# Browser: mirror server aliases and evidence precedence exactly.
path = "card_identity_recognition.js"
src = read(path)
src = replace_once(
    src,
    "function normalizeRegion(value){const r=generationText(value).replace(/\\s+/g,'');if(['JP','JAPAN','JAPANESE','日本','日版','日本版'].includes(r))return 'JP';if(['US','USA','EN','ENGLISH','영문판','미국판'].includes(r))return 'US';if(['KR','KOREA','KOREAN','한국','한국판','한글판'].includes(r))return 'KR';return 'UNKNOWN'}",
    "function normalizeRegion(value){const r=generationText(value).replace(/\\s+/g,'');if(['JP','JPN','JAPAN','JAPANESE','日本','日版','日本版','일본판','일판'].includes(r))return 'JP';if(['US','USA','EN','ENG','ENGLISH','영문판','영판','미국판'].includes(r))return 'US';if(['KR','KOR','KOREA','KOREAN','한국','한국판','한글판','한판','국판'].includes(r))return 'KR';return 'UNKNOWN'}",
    "browser normalizeRegion aliases",
)
src = replace_once(
    src,
    ''' if(/(?:\\b(?:KR|KOREA|KOREAN)\\b|한국판|한글판|국판)/i.test(upper))add('KR','explicit_region_label',.99);\n if(/(?:\\b(?:JP|JAPAN|JAPANESE)\\b|日本版|日版)/i.test(upper))add('JP','explicit_region_label',.99);\n if(/(?:\\b(?:US|USA|ENGLISH)\\b|영문판|미국판)/i.test(upper))add('US','explicit_region_label',.99);\n const hangul=(raw.match(/[가-힣]/g)||[]).length,kana=(raw.match(/[ぁ-んァ-ヶー]/g)||[]).length;\n if(hangul>=2)add('KR','hangul_script',.96,{count:hangul});\n if(kana>=2)add('JP','kana_script',.96,{count:kana});\n''',
    ''' const explicit=[];\n if(/(?:\\b(?:KR|KOR|KOREA|KOREAN)\\b|한국판|한글판|한판|국판)/i.test(upper)){add('KR','explicit_region_label',.99);explicit.push('KR')}\n if(/(?:\\b(?:JP|JPN|JAPAN|JAPANESE)\\b|日本版|日版|일본판|일판)/i.test(upper)){add('JP','explicit_region_label',.99);explicit.push('JP')}\n if(/(?:\\b(?:US|USA|EN|ENG|ENGLISH)\\b|영문판|영판|미국판)/i.test(upper)){add('US','explicit_region_label',.99);explicit.push('US')}\n if(!explicit.length){\n  const hangul=(raw.match(/[가-힣]/g)||[]).length,kana=(raw.match(/[ぁ-んァ-ヶー]/g)||[]).length;\n  if(hangul>=2)add('KR','hangul_script',.96,{count:hangul});\n  if(kana>=2)add('JP','kana_script',.96,{count:kana});\n }\n''',
    "browser explicit label precedence",
)
write(path, src)


# Rotate PWA cache because card_identity_recognition.js is a precached runtime asset.
path = "sw.js"
src = read(path)
src = replace_once(
    src,
    "// v276 rotates the tablet/PWA runtime cache so the latest navigation UI is pre-cached after upgrade.\nconst CACHE='tcg-v276-network-first-runtime';",
    "// v319 rotates the tablet/PWA runtime cache for KR/JP/EN card-region alias precision.\nconst CACHE='tcg-v319-card-region-alias';",
    "service worker cache token",
)
write(path, src)


# Keep the current-runtime gate aware of the new regression.
path = "verify_current_runtime.py"
src = read(path)
needle = '"test_card_identity_market_precision_v309.py","test_card_region_conflict_failclosed_v318.py"'
replacement = '"test_card_identity_market_precision_v309.py","test_card_region_conflict_failclosed_v318.py","test_card_region_label_alias_v319.py"'
count = src.count(needle)
if count < 2:
    raise RuntimeError(f"verify_current_runtime expected >=2 v318 anchors, found {count}")
src = src.replace(needle, replacement)
write(path, src)


# Dedicated regression: user-facing Korean collector shorthand must agree between
# server/browser while true independent evidence conflicts still fail closed.
test = r'''from __future__ import annotations

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
        self.assertIn("const CACHE='tcg-v319-card-region-alias'", sw)
        self.assertIn("'./card_identity_recognition.js'", sw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
'''
write("test_card_region_label_alias_v319.py", test)

print("v319 card-region alias precision patch applied")

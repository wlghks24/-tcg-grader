#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_exact(path: str, old: str, new: str, expected: int = 1) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    found = text.count(old)
    if found != expected:
        raise SystemExit(f"{path}: expected {expected} occurrences, found {found}: {old[:120]!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


def main() -> int:
    replace_exact("grade_market_flow.js", "'\"':'&quot'", "'\"':'&quot;'")

    replace_exact(
        "card_identity_recognition.js",
        "const EN_MEGA_CODES=new Set(['MEG','PFL','ASC','POR']);",
        "const EN_MEGA_CODES=new Set(['MEG','PFL','ASC','POR','CRI','PBL']);",
    )
    replace_exact(
        "card_identity_recognition.js",
        "if(EN_MEGA_CODES.has(c))return {generation:9,generation_label:'9세대 계열',series:'MEGA 시리즈',era:'MEGA',set_region:'US'};",
        "if(EN_MEGA_CODES.has(c))return {generation:null,generation_label:'세대 단정 안 함',series:'MEGA Evolution 시리즈',era:'MEGA',set_region:'US'};",
    )
    replace_exact(
        "card_identity_recognition.js",
        "if(/^M\\d/.test(c))return {generation:9,generation_label:'9세대 계열',series:'MEGA 시리즈',era:'MEGA'};",
        "if(/^M\\d/.test(c))return {generation:null,generation_label:'세대 단정 안 함',series:'MEGA 시리즈',era:'MEGA'};",
    )
    replace_exact(
        "card_identity_recognition.js",
        "if(mark==='J')return {generation:9,generation_label:'9세대 계열 보조추정',series:'MEGA/현행 시리즈',era:'MEGA'};",
        "if(mark==='J')return {generation:null,generation_label:'세대 단정 안 함',series:'MEGA/현행 TCG 시기',era:'CURRENT'};",
    )
    replace_exact(
        "card_identity_recognition.js",
        "if(year>=2025)return {generation:9,generation_label:'9세대 계열',series:'SV→MEGA 전환/현행 시기',era:'CURRENT'};",
        "if(year>=2025)return {generation:null,generation_label:'세대 단정 안 함',series:'SV/MEGA 전환·현행 TCG 시기',era:'CURRENT'};",
        expected=2,
    )
    replace_exact(
        "card_identity_recognition.js",
        "MEGA는 별도 TCG 시리즈/블록이므로 세대 계열과 시리즈를 함께 표시합니다.",
        "MEGA는 별도 TCG 시리즈/블록이므로 TCG 시리즈와 포켓몬 세대 번호를 분리해 표시합니다.",
    )
    replace_exact("card_identity_recognition.js", "version:'v302'", "version:'v306'")

    replace_exact(
        "card_identity_recognition.py",
        'REGIONS = {"KR", "JP", "US", "UNKNOWN"}\n',
        'REGIONS = {"KR", "JP", "US", "UNKNOWN"}\n'
        'POKEMON_EN_SET_CODES = (\n'
        '    "SVI", "PAL", "OBF", "MEW", "PAR", "PAF", "TEF", "TWM", "SFA", "SCR", "SSP",\n'
        '    "PRE", "JTG", "DRI", "BLK", "WHT", "MEG", "PFL", "ASC", "POR", "CRI", "PBL",\n'
        ')\n'
        '_POKEMON_EN_SET_PATTERN = "|".join(map(re.escape, POKEMON_EN_SET_CODES))\n'
        '_POKEMON_EN_SET_EVIDENCE_RE = re.compile(\n'
        '    rf"(?<![A-Z0-9])(?:{_POKEMON_EN_SET_PATTERN})\\s*[- ]?\\s*\\d{{1,3}}(?:\\s*/\\s*\\d{{2,3}})?(?![A-Z0-9])",\n'
        '    re.I,\n'
        ')\n',
    )

    old_prefix = "OP|ST|EB|PRB|P|CP|FB|SV|SM|S"
    new_prefix = (
        "MEG|PFL|ASC|POR|CRI|PBL|SVI|PAL|OBF|MEW|PAR|PAF|TEF|TWM|SFA|SCR|SSP|PRE|JTG|DRI|BLK|WHT|"
        "OP|ST|EB|PRB|P|CP|FB|SV|SM|S"
    )
    path = ROOT / "card_identity_recognition.py"
    text = path.read_text(encoding="utf-8")
    found = text.count(old_prefix)
    if found != 4:
        raise SystemExit(f"card_identity_recognition.py: expected 4 legacy prefix groups, found {found}")
    path.write_text(text.replace(old_prefix, new_prefix), encoding="utf-8")

    replace_exact(
        "card_identity_recognition.py",
        'def normalize_region(value: Any) -> str:\n    region = str(value or "").strip().upper()\n    return region if region in REGIONS else "UNKNOWN"\n',
        'def normalize_region(value: Any) -> str:\n'
        '    region = str(value or "").strip().upper()\n'
        '    return region if region in REGIONS else "UNKNOWN"\n\n\n'
        'def infer_region_from_text(value: Any) -> str:\n'
        '    """Infer KR/JP/US only from strong OCR evidence; otherwise fail closed."""\n'
        '    text = unicodedata.normalize("NFKC", str(value or ""))\n'
        '    upper = text.upper()\n'
        '    compact = re.sub(r"\\s+", "", upper)\n'
        '    if compact in {"JP", "JAPAN", "JAPANESE", "日本", "日版", "日本版"}:\n'
        '        return "JP"\n'
        '    if compact in {"KR", "KOREA", "KOREAN", "한국", "한국판", "한글판"}:\n'
        '        return "KR"\n'
        '    if compact in {"US", "USA", "EN", "ENGLISH", "영문판", "미국판"}:\n'
        '        return "US"\n'
        '    hangul = len(re.findall(r"[가-힣]", text))\n'
        '    kana = len(re.findall(r"[ぁ-んァ-ヶー]", text))\n'
        '    if hangul >= 2 and hangul >= kana:\n'
        '        return "KR"\n'
        '    if kana >= 2:\n'
        '        return "JP"\n'
        '    if _POKEMON_EN_SET_EVIDENCE_RE.search(upper):\n'
        '        return "US"\n'
        '    return "UNKNOWN"\n',
    )

    replace_exact(
        "card_identity_recognition.py",
        '        if region in {"KR", "JP", "US"} and row.get("region") in {"KR", "JP", "US"}:\n            score += 0.012 if row["region"] == region else -0.035\n',
        '        row_region = normalize_region(row.get("region"))\n'
        '        if region in {"KR", "JP", "US"} and row_region in {"KR", "JP", "US"}:\n'
        '            if row_region != region:\n'
        '                continue\n'
        '            score += 0.012\n',
    )
    replace_exact(
        "card_identity_recognition.py",
        'def match_learning(image_hash: str, game: str) -> list[dict[str, Any]]:\n',
        'def match_learning(image_hash: str, game: str, region: str = "UNKNOWN") -> list[dict[str, Any]]:\n',
    )
    replace_exact(
        "card_identity_recognition.py",
        '    rows = [row for row in learning_payload().get("confirmed", []) if isinstance(row, dict) and row.get("game") == game]\n',
        '    requested_region = normalize_region(region)\n'
        '    rows = [\n'
        '        row for row in learning_payload().get("confirmed", [])\n'
        '        if isinstance(row, dict) and row.get("game") == game\n'
        '        and (requested_region == "UNKNOWN" or normalize_region(row.get("region")) in {"UNKNOWN", requested_region})\n'
        '    ]\n',
    )
    replace_exact(
        "card_identity_recognition.py",
        '        supplied_text = (supplied_text + " " + text).strip()[:MAX_OCR_TEXT]\n',
        '        supplied_text = (supplied_text + " " + text).strip()[:MAX_OCR_TEXT]\n'
        '    if region == "UNKNOWN":\n'
        '        inferred_region = infer_region_from_text(supplied_text)\n'
        '        if inferred_region != "UNKNOWN":\n'
        '            region = inferred_region\n',
    )
    replace_exact(
        "card_identity_recognition.py",
        '    learned = match_learning(image_hash, game)\n',
        '    learned = match_learning(image_hash, game, region)\n',
    )

    replace_exact(
        "card_identity_recognition.py",
        '    identity = (card_name, card_number, market_key, game)\n',
        '    identity = (card_name, card_number, market_key, game, region)\n',
    )
    replace_exact(
        "card_identity_recognition.py",
        '    if any((row.get("card_name"), row.get("card_number"), row.get("market_key"), row.get("game")) != identity for row in same_hash):\n',
        '    if any((row.get("card_name"), row.get("card_number"), row.get("market_key"), row.get("game"), normalize_region(row.get("region"))) != identity for row in same_hash):\n',
    )
    replace_exact(
        "card_identity_recognition.py",
        '    keys = {(item.get("image_hash"), item.get("card_name"), item.get("card_number"), item.get("market_key"), item.get("game"))\n            for item in data["confirmed"]}\n    if (image_hash, card_name, card_number, market_key, game) not in keys:\n',
        '    keys = {(item.get("image_hash"), item.get("card_name"), item.get("card_number"), item.get("market_key"), item.get("game"), normalize_region(item.get("region")))\n            for item in data["confirmed"]}\n    if (image_hash, card_name, card_number, market_key, game, region) not in keys:\n',
    )
    replace_exact(
        "card_identity_recognition.py",
        '    count = sum(1 for item in data["confirmed"] if (item.get("card_name"), item.get("card_number"), item.get("market_key"), item.get("game")) == identity)\n',
        '    count = sum(1 for item in data["confirmed"] if (item.get("card_name"), item.get("card_number"), item.get("market_key"), item.get("game"), normalize_region(item.get("region"))) == identity)\n',
    )

    for filename in (
        "test_card_core_crosscheck_v292.py",
        "test_pokemon_generation_display_v207.py",
        "test_card_tablet_runtime_v300.py",
        "test_card_edition_precision_v302.py",
    ):
        target = ROOT / filename
        text = target.read_text(encoding="utf-8")
        text = text.replace("version:'v302'", "version:'v306'")
        text = text.replace("Pokémon generation runtime v302: PASS", "Pokémon generation runtime v306: PASS")
        target.write_text(text, encoding="utf-8")

    target = ROOT / "verify_pokemon_generation_runtime.js"
    text = target.read_text(encoding="utf-8")
    replacements = (
        ("eq(r.generation,9,'reg J generation');ok(/MEGA/.test(r.series),'reg J series should identify current MEGA era');",
         "eq(r.generation,null,'reg J must not invent generation');ok(/MEGA/.test(r.series),'reg J series should identify current MEGA era');"),
        ("eq(r.generation,9,'MEGA generation');eq(r.series,'MEGA 시리즈','MEGA series');",
         "eq(r.generation,null,'MEGA series must not invent generation');eq(r.series,'MEGA 시리즈','MEGA series');"),
        ("eq(r.generation,9,'English MEGA generation');eq(r.series,'MEGA 시리즈','English MEGA series');",
         "eq(r.generation,null,'English MEGA must not invent generation');eq(r.series,'MEGA Evolution 시리즈','English MEGA series');"),
    )
    for old, new in replacements:
        if old not in text:
            raise SystemExit(f"verify_pokemon_generation_runtime.js missing expected contract: {old}")
        text = text.replace(old, new, 1)
    marker = "r=api.infer({game:'pokemon',ocr_text:'©2021 Pokémon'});"
    extra = """r=api.infer({game:'pokemon',ocr_text:'Mega Greninja ex CRI 22'});\neq(r.generation,null,'Chaos Rising must not invent generation');eq(r.series,'MEGA Evolution 시리즈','Chaos Rising series');eq(r.expansion_code,'CRI','Chaos Rising code');\n\nr=api.infer({game:'pokemon',ocr_text:'Pitch Black PBL 79'});\neq(r.generation,null,'Pitch Black must not invent generation');eq(r.expansion_code,'PBL','Pitch Black code');\n\nr=api.infer({game:'pokemon',ocr_text:'©2026 Pokémon',region:'US'});\neq(r.generation,null,'2026 year-only evidence must not invent generation');eq(r.confidence_level,'low','2026 year-only confidence');\n\n"""
    if marker not in text:
        raise SystemExit("verify_pokemon_generation_runtime.js: insertion marker missing")
    text = text.replace(marker, extra + marker, 1)
    text = text.replace("eq(api.version,'v302'", "eq(api.version,'v306'")
    text = text.replace("Pokémon generation runtime v302: PASS", "Pokémon generation runtime v306: PASS")
    target.write_text(text, encoding="utf-8")

    target = ROOT / "verify_current_runtime.py"
    text = target.read_text(encoding="utf-8")
    if "test_card_region_generation_precision_v306.py" not in text:
        text = text.replace(
            '"test_card_tablet_runtime_v300.py","test_card_edition_precision_v302.py",',
            '"test_card_tablet_runtime_v300.py","test_card_edition_precision_v302.py","test_card_region_generation_precision_v306.py",',
        )
        text = text.replace(
            '"test_pokemon_generation_display_v207.py","test_card_edition_precision_v302.py"],360,False)',
            '"test_pokemon_generation_display_v207.py","test_card_edition_precision_v302.py","test_card_region_generation_precision_v306.py"],360,False)',
        )
    text = text.replace(
        "current-main-v302-edition-ocr-generation-gated",
        "current-main-v306-region-generation-precision-gated",
    )
    target.write_text(text, encoding="utf-8")

    (ROOT / "test_card_region_generation_precision_v306.py").write_text(
        r'''from __future__ import annotations

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
        self.assertIn('identity = (card_name, card_number, market_key, game, region)', source)
        self.assertIn('normalize_region(row.get("region"))) != identity', source)

    def test_market_html_escape_and_exact_grade_contract(self) -> None:
        source=(ROOT/'grade_market_flow.js').read_text(encoding='utf-8')
        self.assertIn("'\\\"':'&quot;'", source)
        self.assertIn('!Number.isInteger(exact)', source)
        self.assertIn('다른 판본 가격은 자동 대체하지 않습니다.', source)

    def test_generation_runtime(self) -> None:
        proc=subprocess.run(['node','verify_pokemon_generation_runtime.js'],cwd=ROOT,text=True,capture_output=True,timeout=30,check=False)
        self.assertEqual(0,proc.returncode,proc.stdout+proc.stderr)
        self.assertIn('Pokémon generation runtime v306: PASS',proc.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
''',
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

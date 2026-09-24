#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


# Preserve the long-standing Tesseract language ordering. The v309 accuracy
# work does not require changing OCR engine language precedence.
path = "card_identity_recognition.py"
src = read(path)
src = replace_once(
    src,
    '''    region = normalize_region(region)
    if region == "KR":
        preferred = ["kor", "eng"]
    elif region == "JP":
        preferred = ["jpn", "eng"]
    else:
        preferred = ["eng"]
        if multilingual_fallback:
            preferred.extend(("kor", "jpn"))
''',
    '''    preferred = ["eng"]
    region = normalize_region(region)
    if region == "KR":
        preferred.append("kor")
    elif region == "JP":
        preferred.append("jpn")
    elif multilingual_fallback:
        preferred.extend(("kor", "jpn"))
''',
    "restore OCR language order",
)
write(path, src)

# Update legacy static assertions to the newer semantic contract rather than
# weakening or deleting them.
path = "test_card_region_generation_precision_v306.py"
src = read(path)
src = replace_once(
    src,
    '''        self.assertIn('identity = (card_name, card_number, market_key, game, region)', source)
        self.assertIn('normalize_region(row.get("region"))) != identity', source)
''',
    '''        self.assertIn('core_identity = (card_name, card_number, market_key, game)', source)
        self.assertIn('identity = (*core_identity, effective_region)', source)
        self.assertIn('with exclusive_file_lock(LEARNING', source)
        self.assertIn('same_image_conflicting_identity_or_edition', source)
''',
    "v306 confirmation identity assertions",
)
write(path, src)

path = "test_card_edition_precision_v302.py"
src = read(path)
src = replace_once(
    src,
    '''        self.assertIn("if(kana>=2)return {region:'JP'", source)
        self.assertIn("if(hangul>=2&&hangul>=kana)return {region:'KR'", source)
        self.assertIn("if(englishSet)return {region:'US'", source)
''',
    '''        self.assertIn("if(hangul>=2&&kana>=2)return {region:'UNKNOWN'", source)
        self.assertIn("mixed_script_conflict", source)
        self.assertIn("if(kana>=2)return {region:'JP'", source)
        self.assertIn("if(hangul>=2)return {region:'KR'", source)
        self.assertIn("if(englishSet)return {region:'US'", source)
''',
    "v302 mixed script assertions",
)
write(path, src)

path = "test_card_core_crosscheck_v292.py"
src = read(path).replace("version:'v306'", "version:'v309'")
write(path, src)

path = "test_card_tablet_runtime_v300.py"
src = read(path).replace("version:'v306'", "version:'v309'")
src = replace_once(
    src,
    '''            "wanted==='UNKNOWN'||marketKeyEdition(direct)===wanted",
            "if(wanted!=='UNKNOWN'&&actual!==wanted)continue",
''',
    '''            "if(!cn||directBlob.includes(cn))return direct",
            "if(cn&&!blob.includes(cn))continue",
            "if(wanted!=='UNKNOWN'&&actual!==wanted)continue",
''',
    "market exact number assertions",
)
src = replace_once(
    src,
    '''            "test_card_edition_precision_v302.py",
            "test_multi_market_price_collector.py",
''',
    '''            "test_card_edition_precision_v302.py",
            "test_card_region_generation_precision_v306.py",
            "test_card_identity_market_precision_v309.py",
            "test_multi_market_price_collector.py",
''',
    "runtime v309 gate assertion",
)
write(path, src)

for path in ("test_ocr_multistage_v16.py", "test_ocr_selfrefine_v15.py"):
    src = read(path).replace("v302-edition-aware-ocr-learning", "v309-edition-isolated-ocr-learning")
    write(path, src)

path = "test_pokemon_generation_display_v207.py"
src = read(path).replace("version:'v306'", "version:'v309'")
src = src.replace("Pokémon generation runtime v306: PASS", "Pokémon generation runtime v309: PASS")
src = replace_once(
    src,
    '''            "identityCoreKey",
            "same photo" if False else "같은 사진에 서로 다른 카드/판본 정보",
''',
    '''            "identityCoreKey",
            "generationConflict",
            "mixed_script_conflict",
            "v309-edition-isolated-ocr-learning",
            "same photo" if False else "같은 사진에 서로 다른 카드/판본 정보",
''',
    "generation display v309 assertions",
)
write(path, src)

# Strengthen the v309 regression itself with the preserved OCR-order contract.
path = "test_card_identity_market_precision_v309.py"
src = read(path)
src = replace_once(
    src,
    '''    def test_server_mixed_scripts_fail_closed(self) -> None:
''',
    '''    def test_multilingual_ocr_order_remains_backward_compatible(self) -> None:
        from unittest import mock
        with mock.patch.object(identity, "_tesseract_languages", return_value=frozenset({"eng", "kor", "jpn"})):
            self.assertEqual("eng+kor", identity._ocr_language("KR"))
            self.assertEqual("eng+jpn", identity._ocr_language("JP"))
            self.assertEqual("eng+kor+jpn", identity._ocr_language("UNKNOWN", multilingual_fallback=True))

    def test_server_mixed_scripts_fail_closed(self) -> None:
''',
    "v309 OCR compatibility test",
)
write(path, src)

print("v309 compatibility repair prepared")

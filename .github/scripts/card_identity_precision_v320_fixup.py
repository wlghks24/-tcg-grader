#!/usr/bin/env python3
from pathlib import Path

path = Path(__file__).resolve().parent / "card_identity_precision_v320.py"
text = path.read_text(encoding="utf-8")
replacements = [
    ("function generationRegion(value)''',\n        \"regulation semantics\"", "''',\n        \"regulation semantics\""),
    ("function inferPokemonGeneration(input={}){''',\n        \"generation conflict semantics\"", "''',\n        \"generation conflict semantics\""),
    ("function renderPokemonGeneration(info,game='pokemon'){''',\n        \"generation inference\"", "''',\n        \"generation inference\""),
    ("window.TCGPokemonGeneration=Object.freeze''',\n        \"generation render\"", "''',\n        \"generation render\""),
    ("async function recognize(game){''',\n        \"candidate application\"", "''',\n        \"candidate application\""),
    ("function identityCoreKey(item){''',\n        \"browser recognition\"", "''',\n        \"browser recognition\""),
]
for old, new in replacements:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"temporary patch marker expected once, got {count}: {old[:50]}")
    text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print("v320 temporary patch markers repaired")

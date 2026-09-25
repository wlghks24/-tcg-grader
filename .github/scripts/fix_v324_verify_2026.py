#!/usr/bin/env python3
from pathlib import Path

path=Path('verify_pokemon_generation_runtime.js')
text=path.read_text(encoding='utf-8')
old="""r=api.infer({game:'pokemon',ocr_text:'©2026 Pokémon',region:'US'});\neq(r.generation,null,'2026 year-only evidence must not invent generation');eq(r.confidence_level,'low','2026 year-only confidence');\n"""
new="""r=api.infer({game:'pokemon',ocr_text:'©2026 Pokémon',region:'US'});\neq(r.generation,null,'2026 year-only evidence must not invent generation');eq(r.generation_hint,null,'2026 transition era must not invent generation hint');eq(r.status,'context_only','2026 year-only context status');eq(r.confidence_level,'context','2026 year-only confidence');\n"""
if old not in text:
    raise SystemExit('2026 generation expectation block not found')
path.write_text(text.replace(old,new,1),encoding='utf-8')
print('v324 2026 year-only expectation aligned')

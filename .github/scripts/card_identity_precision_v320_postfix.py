#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[2]
path = root / "verify_pokemon_generation_runtime.js"
text = path.read_text(encoding="utf-8")
old = "r=api.infer({game:'pokemon',ocr_text:'REGULATION MARK J'});\neq(r.generation,null,'reg J must not invent generation');ok(/MEGA/.test(r.series),'reg J series should identify current MEGA era');"
new = "r=api.infer({game:'pokemon',ocr_text:'REGULATION MARK J'});\neq(r.generation,null,'reg J must not invent generation');eq(r.status,'context_only','reg J context status');eq(r.regulation_mark,'J','reg J mark');ok(/레귤레이션 J/.test(r.series),'reg J remains regulation context');"
if text.count(old) != 1:
    raise RuntimeError(f"regulation J contract anchor expected once, got {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("v320 regulation J contract aligned")

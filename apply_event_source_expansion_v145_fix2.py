#!/usr/bin/env python3
from pathlib import Path

p=Path('event_source_expansion_v145.py')
text=p.read_text(encoding='utf-8')
old='replace = next((i for i in range(len(rows) - 1, 2, -1) if rows[i].get("family") == "exploration"), None)'
new='replace = next((i for i in range(len(rows) - 1, 2, -1) if rows[i].get("family") in {"exploration", "official-site"}), None)'
if old not in text:
    if new not in text:
        raise SystemExit('v145 scoped learned-host replacement anchor missing')
else:
    text=text.replace(old,new,1)
    p.write_text(text,encoding='utf-8')
print('[OK] v145 learned-host reservation prefers exploration/official-site slot')

#!/usr/bin/env python3
from pathlib import Path

path = Path('card_identity_recognition.py')
text = path.read_text(encoding='utf-8')
old = '    known = {(row["game"], normalize(row["card_name"]), row["card_number"]) for row in rows}\n'
new = '''    # Catalog identity is edition-specific. The same card name/number may exist\n    # in KR/JP/US; one region must never suppress a verified reference row from\n    # another region.\n    known = {\n        (row["game"], normalize(row["card_name"]), row["card_number"], normalize_region(row.get("region")))\n        for row in rows\n    }\n'''
if text.count(old) != 1:
    raise SystemExit(f'known-key match count={text.count(old)}')
text = text.replace(old, new, 1)
old2 = '        key = (game, normalize(name), number)\n'
new2 = '        key = (game, normalize(name), number, region)\n'
if text.count(old2) != 1:
    raise SystemExit(f'reference-key match count={text.count(old2)}')
text = text.replace(old2, new2, 1)
path.write_text(text, encoding='utf-8')
print('v317 catalog region isolation patch applied')

#!/usr/bin/env python3
from pathlib import Path

INDEX = Path('index.html')
CSS_HREF = './purchase_ui_polish.css?v=119'
LINK = f'<link rel="stylesheet" href="{CSS_HREF}">'

text = INDEX.read_text(encoding='utf-8')
if LINK not in text:
    marker = '</head>'
    if marker not in text:
        raise SystemExit('missing </head>')
    text = text.replace(marker, LINK + '\n' + marker, 1)
    INDEX.write_text(text, encoding='utf-8')

# validation
out = INDEX.read_text(encoding='utf-8')
assert LINK in out
assert 'purchase-channel-tabs' in out
assert 'purchaseRegionGrid' in out
print('OK purchase UI polish linked')

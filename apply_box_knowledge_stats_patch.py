#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parent
INDEX=ROOT/'index.html'
UPDATER=ROOT/'tcg_updater.py'


def patch_index():
    text=INDEX.read_text(encoding='utf-8')
    if 'box_knowledge_stats.css' not in text:
        marker='</head>'
        if marker not in text: raise SystemExit('index head marker missing')
        text=text.replace(marker,'<link rel="stylesheet" href="box_knowledge_stats.css">\n'+marker,1)
    if 'box_knowledge_stats.js' not in text:
        marker='</body></html>'
        if marker not in text: raise SystemExit('index body marker missing')
        text=text.replace(marker,'<script src="box_knowledge_stats.js"></script>\n'+marker,1)
    INDEX.write_text(text,encoding='utf-8')


def patch_updater():
    text=UPDATER.read_text(encoding='utf-8')
    if "'box_knowledge_stats.js'" not in text:
        old="'market_catalog_expander.js'"
        if old not in text: raise SystemExit('static file marker missing')
        text=text.replace(old,old+",'box_knowledge_stats.js','box_knowledge_stats.css'",1)
    UPDATER.write_text(text,encoding='utf-8')


if __name__=='__main__':
    patch_index();patch_updater();print('BOX knowledge statistics integration patched')

#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parent
INDEX=ROOT/'index.html'
UPDATER=ROOT/'tcg_updater.py'


def patch_index():
    text=INDEX.read_text(encoding='utf-8')
    tag='<script src="image_quality_guard.js"></script>'
    if tag not in text:
        marker='<script src="market_catalog_expander.js"></script>'
        if marker not in text: raise SystemExit('market catalog script marker missing')
        text=text.replace(marker,marker+'\n'+tag,1)
        INDEX.write_text(text,encoding='utf-8')


def patch_updater():
    text=UPDATER.read_text(encoding='utf-8')
    if "'image_quality_guard.js'" not in text:
        old="'graded_photo_dashboard.js','graded_photo_dashboard.css','market_catalog_expander.js'"
        new="'graded_photo_dashboard.js','graded_photo_dashboard.css','market_catalog_expander.js','image_quality_guard.js'"
        if old not in text: raise SystemExit('public static marker missing')
        text=text.replace(old,new,1)
        UPDATER.write_text(text,encoding='utf-8')


if __name__=='__main__':
    patch_index();patch_updater();print('image quality guard integrated')
from pathlib import Path

# 1) market-price collector: merge promoted multi-market BOX/HIT discoveries.
p=Path('update_market_prices.py');t=p.read_text(encoding='utf-8')
needle="    try:\n        from market_public_crosscheck import crosscheck_market_db\n        crosscheck_market_db(db)\n"
insert="    try:\n        from box_hit_market_discovery import merge_market_catalog\n        merge_market_catalog(db)\n    except Exception as e:\n        errors.append('BOX/HIT 다중마켓 자동발견: '+type(e).__name__)\n    try:\n        from market_public_crosscheck import crosscheck_market_db\n        crosscheck_market_db(db)\n"
if 'merge_market_catalog(db)' not in t:
    if needle not in t:raise SystemExit('update_market_prices integration target missing')
    t=t.replace(needle,insert,1);p.write_text(t,encoding='utf-8')

# 2) browser: load dynamic market catalog after all inline catalog/render functions exist.
p=Path('index.html');t=p.read_text(encoding='utf-8')
tag='<script src="market_catalog_expander.js"></script>'
if tag not in t:
    pos=t.lower().rfind('</body>')
    if pos<0:raise SystemExit('index body close missing')
    t=t[:pos]+tag+'\n'+t[pos:];p.write_text(t,encoding='utf-8')

# 3) tablet server static allowlist.
p=Path('tcg_updater.py');t=p.read_text(encoding='utf-8')
if "'market_catalog_expander.js'" not in t:
    target="'graded_photo_dashboard.js','graded_photo_dashboard.css'"
    repl=target+",'market_catalog_expander.js'"
    if target not in t:raise SystemExit('static allowlist target missing')
    t=t.replace(target,repl,1);p.write_text(t,encoding='utf-8')

print('BOX/HIT multi-market expansion integrated')

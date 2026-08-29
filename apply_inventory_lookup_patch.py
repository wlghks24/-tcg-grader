from pathlib import Path

root=Path(__file__).resolve().parent
index=root/'index.html'
server=root/'tcg_updater.py'

html=index.read_text(encoding='utf-8')
css='<link rel="stylesheet" href="inventory_lookup.css">'
js='<script src="inventory_lookup.js"></script>'
if css not in html:
    html=html.replace('</head>',css+'\n</head>',1)
if js not in html:
    html=html.replace('</body>',js+'\n</body>',1)
index.write_text(html,encoding='utf-8')

py=server.read_text(encoding='utf-8')
if "'inventory_lookup.js'" not in py:
    py=py.replace("'purchase_sources.json','purchase_signals.json','exchange_rates.json'", "'purchase_sources.json','purchase_signals.json','exchange_rates.json','inventory_lookup.js','inventory_lookup.css'",1)
route="""        if path=='/api/inventory-lookup':
            qs=parse_qs(parsed.query)
            q=qs.get('q',[''])[0].strip(); game=qs.get('game',[''])[0].strip()
            if len(q)>120 or len(game)>40:
                return self.json({'ok':False,'error':'재고조회 조건 오류','items':[]},400)
            if not self._search_origin_allowed():
                return self.json({'ok':False,'error':'허용되지 않은 요청 출처','items':[]},403)
            try:
                from inventory_lookup import get_inventory_options
                return self.json(get_inventory_options(q,game))
            except Exception:
                return self.json({'ok':False,'error':'공식 재고조회 엔진 오류','items':[]},500)
"""
needle="        if path=='/api/purchase-live-search':\n"
if route not in py:
    if needle not in py: raise SystemExit('purchase route anchor not found')
    py=py.replace(needle,route+needle,1)
server.write_text(py,encoding='utf-8')

assert css in html and js in html
assert "path=='/api/inventory-lookup'" in py
print('inventory lookup patch applied')

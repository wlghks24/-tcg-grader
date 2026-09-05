from pathlib import Path
import re

# Link browser assets.
p=Path('index.html')
s=p.read_text(encoding='utf-8')
css='<link rel="stylesheet" href="multi_market_prices.css">'
js='<script src="multi_market_prices.js"></script>'
css_pattern=re.compile(r'''<link\s+rel=["']stylesheet["']\s+href=["']multi_market_prices\.css(?:\?[^"']*)?["']\s*/?>''',re.I)
js_pattern=re.compile(r'''<script\s+src=["']multi_market_prices\.js(?:\?[^"']*)?["']\s*></script>''',re.I)
if not css_pattern.search(s):
    if '</head>' not in s: raise SystemExit('missing </head>')
    s=s.replace('</head>',css+'\n</head>',1)
if not js_pattern.search(s):
    marker='<script src="auto_market_center.js"></script>'
    if marker in s:s=s.replace(marker,marker+'\n'+js,1)
    elif '</body>' in s:s=s.replace('</body>',js+'\n</body>',1)
    else:raise SystemExit('missing body close')
p.write_text(s,encoding='utf-8')

# Serve assets and add API route.
p=Path('tcg_updater.py')
s=p.read_text(encoding='utf-8')
needle="'auto_market_center.js','auto_market_center.css'"
replacement="'auto_market_center.js','auto_market_center.css','multi_market_prices.js','multi_market_prices.css'"
if replacement not in s:
    if needle not in s: raise SystemExit('missing static anchor')
    s=s.replace(needle,replacement,1)
route_anchor="        if path=='/api/grading-proxy-costs':\n"
route="""        if path=='/api/multi-market-prices':
            qs=parse_qs(parsed.query)
            q=(qs.get('q',[''])[0] or '')[:160]
            region=(qs.get('region',['ALL'])[0] or 'ALL')[:8]
            game=(qs.get('game',['ALL'])[0] or 'ALL')[:40]
            force=qs.get('force',['0'])[0]=='1'
            if not self._search_origin_allowed():
                return self.json({'ok':False,'error':'허용되지 않은 요청 출처','items':[]},403)
            try:
                from multi_market_price_collector import search_multi_market
                return self.json(search_multi_market(q,region=region,game=game,force=force))
            except Exception:
                return self.json({'ok':False,'error':'다중마켓 시세수집 엔진 오류','items':[]},500)
"""
if "/api/multi-market-prices" not in s:
    if route_anchor not in s: raise SystemExit('missing API route anchor')
    s=s.replace(route_anchor,route+route_anchor,1)
p.write_text(s,encoding='utf-8')

# Keep runtime caches out of git while preserving local learning across pulls.
p=Path('.gitignore')
s=p.read_text(encoding='utf-8') if p.exists() else ''
for line in ['multi_market_price_cache.json','multi_market_source_learning.json']:
    if line not in s.splitlines():s += ('\n' if s and not s.endswith('\n') else '')+line+'\n'
p.write_text(s,encoding='utf-8')
print('multi-market prices integrated')

from pathlib import Path

root=Path(__file__).resolve().parent
index=root/'index.html'; server=root/'tcg_updater.py'
html=index.read_text(encoding='utf-8')
css='<link rel="stylesheet" href="grading_proxy_costs.css">'; js='<script src="grading_proxy_costs.js"></script>'
if css not in html: html=html.replace('</head>',css+'\n</head>',1)
if js not in html: html=html.replace('</body>',js+'\n</body>',1)
index.write_text(html,encoding='utf-8')

py=server.read_text(encoding='utf-8')
# Static file allowlist
if "'grading_proxy_costs.js'" not in py:
    py=py.replace("'inventory_lookup.js','inventory_lookup.css'", "'inventory_lookup.js','inventory_lookup.css','grading_proxy_costs.js','grading_proxy_costs.css'",1)
route="""        if path=='/api/grading-proxy-costs':
            qs=parse_qs(parsed.query)
            force=qs.get('force',['0'])[0]=='1'
            if not self._search_origin_allowed():
                return self.json({'ok':False,'error':'허용되지 않은 요청 출처','providers':[]},403)
            try:
                from grading_proxy_costs import get_proxy_costs
                return self.json(get_proxy_costs(force=force))
            except Exception:
                return self.json({'ok':False,'error':'등급대행 비용 엔진 오류','providers':[]},500)
"""
needle="        if path=='/api/grading-costs':\n"
if route not in py:
    if needle in py: py=py.replace(needle,route+needle,1)
    else:
        needle="        if path=='/api/inventory-lookup':\n"
        if needle not in py: raise SystemExit('API route anchor not found')
        py=py.replace(needle,route+needle,1)
server.write_text(py,encoding='utf-8')
assert css in html and js in html and "path=='/api/grading-proxy-costs'" in py
print('grading proxy costs patch applied')

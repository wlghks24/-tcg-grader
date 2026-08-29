from pathlib import Path
root=Path(__file__).resolve().parent
index=root/'index.html'; server=root/'tcg_updater.py'
html=index.read_text(encoding='utf-8')
css='<link rel="stylesheet" href="grading_costs_live.css">'; js='<script src="grading_costs_live.js"></script>'
if css not in html: html=html.replace('</head>',css+'\n</head>',1)
if js not in html: html=html.replace('</body>',js+'\n</body>',1)
index.write_text(html,encoding='utf-8')
py=server.read_text(encoding='utf-8')
if "'grading_costs_live.js'" not in py:
    py=py.replace("'inventory_lookup.js','inventory_lookup.css'", "'inventory_lookup.js','inventory_lookup.css','grading_costs_live.js','grading_costs_live.css'",1)
route="""        if path=='/api/grading-costs':
            if not self._search_origin_allowed():
                return self.json({'ok':False,'error':'허용되지 않은 요청 출처'},403)
            try:
                from grading_costs_live import get_grading_costs
                return self.json(get_grading_costs())
            except Exception:
                return self.json({'ok':False,'error':'감정비 조회 엔진 오류'},500)
"""
needle="        if path=='/api/inventory-lookup':\n"
if route not in py:
    if needle not in py: raise SystemExit('inventory route anchor missing')
    py=py.replace(needle,route+needle,1)
server.write_text(py,encoding='utf-8')
assert "path=='/api/grading-costs'" in py and css in html and js in html
print('grading costs integration applied')

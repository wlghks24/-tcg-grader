from pathlib import Path

root=Path(__file__).resolve().parent
index=root/'index.html'
server=root/'tcg_updater.py'
html=index.read_text(encoding='utf-8')
css='<link rel="stylesheet" href="grading_total_cost.css">'
js='<script src="grading_total_cost.js"></script>'
if css not in html:
    html=html.replace('</head>',css+'\n</head>',1)
if js not in html:
    html=html.replace('</body>',js+'\n</body>',1)
index.write_text(html,encoding='utf-8')
py=server.read_text(encoding='utf-8')
anchor="'grading_proxy_costs.js','grading_proxy_costs.css'"
replacement="'grading_proxy_costs.js','grading_proxy_costs.css','grading_total_cost.js','grading_total_cost.css'"
if "'grading_total_cost.js'" not in py:
    if anchor not in py: raise SystemExit('static allowlist anchor missing')
    py=py.replace(anchor,replacement,1)
server.write_text(py,encoding='utf-8')
assert css in html and js in html and "'grading_total_cost.js'" in py
print('grading total cost patch applied')

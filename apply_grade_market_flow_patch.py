from pathlib import Path

root=Path(__file__).resolve().parent
index=root/'index.html'
server=root/'tcg_updater.py'

s=index.read_text(encoding='utf-8')
css='<link rel="stylesheet" href="grade_market_flow.css">'
js='<script src="grade_market_flow.js"></script>'
if css not in s:
    if '</head>' not in s: raise SystemExit('missing </head>')
    s=s.replace('</head>',css+'\n</head>',1)
if js not in s:
    if '</body>' not in s: raise SystemExit('missing </body>')
    s=s.replace('</body>',js+'\n</body>',1)
index.write_text(s,encoding='utf-8')

py=server.read_text(encoding='utf-8')
needle="'inventory_lookup.js','inventory_lookup.css'"
replacement="'inventory_lookup.js','inventory_lookup.css','grade_market_flow.js','grade_market_flow.css'"
if "'grade_market_flow.js'" not in py or "'grade_market_flow.css'" not in py:
    if needle not in py:
        raise SystemExit('static allowlist anchor not found')
    py=py.replace(needle,replacement,1)
server.write_text(py,encoding='utf-8')

assert css in s and js in s
assert "'grade_market_flow.js'" in py and "'grade_market_flow.css'" in py
print('grade market flow linked and server allowlist updated')

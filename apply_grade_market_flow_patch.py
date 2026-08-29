from pathlib import Path

p=Path('index.html')
s=p.read_text(encoding='utf-8')
css='<link rel="stylesheet" href="grade_market_flow.css">'
js='<script src="grade_market_flow.js"></script>'
if css not in s:
    if '</head>' not in s: raise SystemExit('missing </head>')
    s=s.replace('</head>',css+'\n</head>',1)
if js not in s:
    if '</body>' not in s: raise SystemExit('missing </body>')
    s=s.replace('</body>',js+'\n</body>',1)
p.write_text(s,encoding='utf-8')
print('grade market flow linked')

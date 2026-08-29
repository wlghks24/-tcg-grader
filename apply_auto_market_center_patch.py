from pathlib import Path

# Link browser assets.
p=Path('index.html')
s=p.read_text(encoding='utf-8')
css='<link rel="stylesheet" href="auto_market_center.css">'
js='<script src="auto_market_center.js"></script>'
if css not in s:
    if '</head>' not in s: raise SystemExit('missing </head>')
    s=s.replace('</head>',css+'\n</head>',1)
if js not in s:
    marker='<script src="grade_market_flow.js"></script>'
    if marker in s:
        s=s.replace(marker,marker+'\n'+js,1)
    elif '</body>' in s:
        s=s.replace('</body>',js+'\n</body>',1)
    else: raise SystemExit('missing body close')
p.write_text(s,encoding='utf-8')

# Allow tablet/PC server to serve the new assets.
p=Path('tcg_updater.py')
s=p.read_text(encoding='utf-8')
needle="'grade_market_flow.js','grade_market_flow.css'"
replacement="'grade_market_flow.js','grade_market_flow.css','auto_market_center.js','auto_market_center.css'"
if replacement not in s:
    if needle not in s: raise SystemExit('missing PUBLIC_STATIC_FILES anchor')
    s=s.replace(needle,replacement,1)
p.write_text(s,encoding='utf-8')
print('auto market center integrated')

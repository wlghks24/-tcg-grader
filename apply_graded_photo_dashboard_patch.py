from pathlib import Path

idx=Path('index.html')
text=idx.read_text(encoding='utf-8')
css='<link rel="stylesheet" href="graded_photo_dashboard.css">'
js='<script src="graded_photo_dashboard.js"></script>'
if css not in text:
    marker='</head>'
    text=text.replace(marker,css+'\n'+marker,1)
if js not in text:
    marker='</body>'
    text=text.replace(marker,js+'\n'+marker,1)
idx.write_text(text,encoding='utf-8')

srv=Path('tcg_updater.py')
s=srv.read_text(encoding='utf-8')
needle="'auto_validation_flow.js','auto_validation_flow.css'"
if 'graded_photo_dashboard.js' not in s:
    if needle not in s:
        raise SystemExit('static allowlist anchor not found')
    s=s.replace(needle,needle+",'graded_photo_dashboard.js','graded_photo_dashboard.css'",1)
srv.write_text(s,encoding='utf-8')
print('graded photo dashboard integrated')

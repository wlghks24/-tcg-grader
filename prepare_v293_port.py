from pathlib import Path

path = Path('apply_v293_card_core.py')
text = path.read_text(encoding='utf-8')
start = text.find("replace_exact(index,\n    ' if(gameFilter")
if start < 0:
    raise SystemExit('v293 period patch block start not found')
end_marker = "    ' const cardName=', count=1)\n"
end = text.find(end_marker, start)
if end < 0:
    raise SystemExit('v293 period patch block end not found')
end += len(end_marker)
text = text[:start] + text[end:]
path.write_text(text, encoding='utf-8')
print('prepared v293 core script: period injection deferred')

from pathlib import Path

path = Path('grade_market_flow.js')
text = path.read_text(encoding='utf-8')
old = "else if(wanted!=='UNKNOWN'&&actual!=='UNKNOWN'&&actual!==wanted)return -999;"
new = "else if(wanted!=='UNKNOWN'&&actual!==wanted)return -999;"
if old not in text:
    if new in text:
        raise SystemExit('v297 patch already applied')
    raise SystemExit('expected v295 market-edition contract not found')
if text.count(old) != 1:
    raise SystemExit(f'unexpected market-edition contract count: {text.count(old)}')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
print('v297 patch applied: known card editions now reject UNKNOWN quote editions')

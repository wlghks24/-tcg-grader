from pathlib import Path
import re

path = Path('index.html')
text = path.read_text(encoding='utf-8')
pattern = re.compile(
    r'(?P<indent>[ \t]*)if\(gameFilter!=="ALL"&&game!==gameFilter\)continue;\r?\n(?P=indent)const cardName='
)
match = pattern.search(text)
if not match:
    raise SystemExit('index.html: v13 game/card anchor not found')
indent = match.group('indent')
replacement = (
    f'{indent}if(gameFilter!=="ALL"&&game!==gameFilter)continue;\n'
    f'{indent}const observedAt=value.source_date||value.observed_on||value.checked_at||w.price_checked_at||w.checked_at||"";\n'
    f'{indent}if(!window.TCGMarketPeriodV293||!TCGMarketPeriodV293.withinPeriod(observedAt,period,Date.now()))continue;\n'
    f'{indent}const cardName='
)
text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit(f'index.html: period patch count={count}')
path.write_text(text, encoding='utf-8')
print('v293 period filter wired')

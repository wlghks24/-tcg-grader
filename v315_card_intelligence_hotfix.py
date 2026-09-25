from pathlib import Path

p=Path('multi_market_price_collector.py')
text=p.read_text(encoding='utf-8')
old="CARD_NUMBER_QUERY_RE=re.compile(r'\\b(?:[A-Z]{1,6}\\d{0,3}[- ]?)?[A-Z]?\\d{1,4}(?:/[A-Z]?\\d{1,4})?\\b',re.I)"
new="""CARD_NUMBER_QUERY_RE=re.compile(\n    r'(?<![A-Z0-9])(?:'\n    r'(?:SVI|PAL|OBF|MEW|PAR|PAF|TEF|TWM|SFA|SCR|SSP|PRE|JTG|DRI|BLK|WHT|MEG|PFL|ASC|POR|CRI|PBL)\\s*-?\\s*\\d{1,4}(?:/\\d{2,4})?'\n    r'|[A-Z]{1,4}\\d{1,3}[A-Z]{0,2}-?\\d{1,4}(?:/\\d{2,4})?'\n    r'|\\d{1,4}/\\d{2,4}'\n    r'|\\d{1,4}'\n    r')(?![A-Z0-9])',re.I\n)"""
if text.count(old)!=1:raise RuntimeError(f'old card regex count={text.count(old)}')
text=text.replace(old,new,1)
old2="""        prefix=text[max(0,match.start()-16):match.start()]\n        if re.search(r'(?:PSA|BGS|CGC|TAG|BRG)\\s*$',prefix,re.I):continue"""
new2="""        prefix=text[max(0,match.start()-16):match.start()]\n        if GRADER_QUERY_RE.fullmatch(token) or re.search(r'(?:PSA|BGS|CGC|TAG|BRG)\\s*$',prefix,re.I):continue"""
if text.count(old2)!=1:raise RuntimeError(f'grader guard count={text.count(old2)}')
text=text.replace(old2,new2,1)
p.write_text(text,encoding='utf-8')
print('v315 query tokenizer hotfix applied')

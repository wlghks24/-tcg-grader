#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def read(path): return (ROOT/path).read_text(encoding='utf-8')
def write(path,text): (ROOT/path).write_text(text,encoding='utf-8')
def replace_once(text,old,new,label):
    count=text.count(old)
    if count!=1: raise SystemExit(f'{label}: expected 1 match, got {count}')
    return text.replace(old,new,1)

p='card_identity_recognition.py'
s=read(p)
s=replace_once(s,
'''def normalize_region(value: Any) -> str:\n    region = str(value or "").strip().upper()\n    return region if region in REGIONS else "UNKNOWN"\n''',
'''def normalize_region(value: Any) -> str:\n    region = unicodedata.normalize("NFKC", str(value or "")).strip().upper().replace(" ", "")\n    aliases = {\n        "KR": "KR", "KOR": "KR", "KOREA": "KR", "KOREAN": "KR",\n        "한국": "KR", "한국판": "KR", "한글판": "KR", "한판": "KR", "국판": "KR",\n        "JP": "JP", "JPN": "JP", "JAPAN": "JP", "JAPANESE": "JP",\n        "日本": "JP", "日本版": "JP", "日版": "JP", "일본판": "JP", "일판": "JP",\n        "US": "US", "USA": "US", "EN": "US", "ENGLISH": "US", "ENG": "US",\n        "영문판": "US", "영판": "US", "미국판": "US",\n        "UNKNOWN": "UNKNOWN",\n    }\n    return aliases.get(region, "UNKNOWN")\n''','python normalize_region')
s=replace_once(s,
'''    explicit_patterns = (\n        ("KR", r"(?:\\b(?:KR|KOREA|KOREAN)\\b|한국판|한글판|국판)"),\n        ("JP", r"(?:\\b(?:JP|JAPAN|JAPANESE)\\b|日本版|日版)"),\n        ("US", r"(?:\\b(?:US|USA|EN|ENGLISH)\\b|영문판|미국판)"),\n    )\n    for region, pattern in explicit_patterns:\n        if re.search(pattern, upper, re.I):\n            signals.append({"region": region, "basis": "explicit_region_label", "confidence": 0.99})\n\n    hangul = len(re.findall(r"[가-힣]", text))\n    kana = len(re.findall(r"[ぁ-んァ-ヶー]", text))\n    if hangul >= 2:\n''',
'''    explicit_patterns = (\n        ("KR", r"(?:\\b(?:KR|KOR|KOREA|KOREAN)\\b|한국판|한글판|한판|국판)"),\n        ("JP", r"(?:\\b(?:JP|JPN|JAPAN|JAPANESE)\\b|日本版|日版|일본판|일판)"),\n        ("US", r"(?:\\b(?:US|USA|EN|ENGLISH|ENG)\\b|영문판|영판|미국판)"),\n    )\n    for region, pattern in explicit_patterns:\n        if re.search(pattern, upper, re.I):\n            signals.append({"region": region, "basis": "explicit_region_label", "confidence": 0.99})\n\n    # Collector-facing Korean labels describe metadata; their Hangul characters\n    # must not create a fake KR signal. Independent kana/set-code evidence still\n    # participates and can force a real cross-edition conflict.\n    suppress_hangul = bool(re.search(r"(?:일본판|일판|영문판|영판|미국판)", text, re.I))\n    hangul = len(re.findall(r"[가-힣]", text))\n    kana = len(re.findall(r"[ぁ-んァ-ヶー]", text))\n    if hangul >= 2 and not suppress_hangul:\n''','python edition aliases')
write(p,s)

p='card_identity_recognition.js'
s=read(p)
s=replace_once(s,
"function normalizeRegion(value){const r=generationText(value).replace(/\\s+/g,'');if(['JP','JAPAN','JAPANESE','日本','日版','日本版'].includes(r))return 'JP';if(['US','USA','EN','ENGLISH','영문판','미국판'].includes(r))return 'US';if(['KR','KOREA','KOREAN','한국','한국판','한글판'].includes(r))return 'KR';return 'UNKNOWN'}",
"function normalizeRegion(value){const r=generationText(value).replace(/\\s+/g,'');if(['JP','JPN','JAPAN','JAPANESE','日本','日版','日本版','일본판','일판'].includes(r))return 'JP';if(['US','USA','EN','ENGLISH','ENG','영문판','영판','미국판'].includes(r))return 'US';if(['KR','KOR','KOREA','KOREAN','한국','한국판','한글판','한판','국판'].includes(r))return 'KR';return 'UNKNOWN'}",
'js normalizeRegion')
s=replace_once(s,
''' if(/(?:\\b(?:KR|KOREA|KOREAN)\\b|한국판|한글판|국판)/i.test(upper))add('KR','explicit_region_label',.99);\n if(/(?:\\b(?:JP|JAPAN|JAPANESE)\\b|日本版|日版)/i.test(upper))add('JP','explicit_region_label',.99);\n if(/(?:\\b(?:US|USA|EN|ENGLISH)\\b|영문판|미국판)/i.test(upper))add('US','explicit_region_label',.99);\n const hangul=(raw.match(/[가-힣]/g)||[]).length,kana=(raw.match(/[ぁ-んァ-ヶー]/g)||[]).length;\n if(hangul>=2)add('KR','hangul_script',.96,{count:hangul});\n''',
''' if(/(?:\\b(?:KR|KOR|KOREA|KOREAN)\\b|한국판|한글판|한판|국판)/i.test(upper))add('KR','explicit_region_label',.99);\n if(/(?:\\b(?:JP|JPN|JAPAN|JAPANESE)\\b|日本版|日版|일본판|일판)/i.test(upper))add('JP','explicit_region_label',.99);\n if(/(?:\\b(?:US|USA|EN|ENGLISH|ENG)\\b|영문판|영판|미국판)/i.test(upper))add('US','explicit_region_label',.99);\n const suppressHangul=/(?:일본판|일판|영문판|영판|미국판)/i.test(raw);\n const hangul=(raw.match(/[가-힣]/g)||[]).length,kana=(raw.match(/[ぁ-んァ-ヶー]/g)||[]).length;\n if(hangul>=2&&!suppressHangul)add('KR','hangul_script',.96,{count:hangul});\n''','js edition aliases')
write(p,s)

p='sw.js'; s=read(p)
s=replace_once(s,
'// v276 rotates the tablet/PWA runtime cache so the latest navigation UI is pre-cached after upgrade.\n',
'// v324 refreshes tablet/PWA identity runtime while preserving the v276 cache ABI.\n',
'service worker refresh')
write(p,s)

p='verify_current_runtime.py'; s=read(p)
needle='"test_card_variant_market_precision_v323.py","test_multi_market_price_collector.py"'
count=s.count(needle)
if count<1: raise SystemExit(f'verify_current_runtime anchor missing: {count}')
s=s.replace(needle,'"test_card_variant_market_precision_v323.py","test_card_collector_edition_alias_v324.py","test_multi_market_price_collector.py"')
write(p,s)
print('v324 patch applied')

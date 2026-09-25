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
'''def normalize_region(value: Any) -> str:\n    region = unicodedata.normalize("NFKC", str(value or "")).strip().upper().replace(" ", "")\n    aliases = {\n        "KR": "KR", "KOR": "KR", "KOREA": "KR", "KOREAN": "KR",\n        "한국": "KR", "한국판": "KR", "한글판": "KR", "한판": "KR", "국판": "KR",\n        "JP": "JP", "JPN": "JP", "JAPAN": "JP", "JAPANESE": "JP",\n        "日本": "JP", "日本版": "JP", "日版": "JP", "일본판": "JP", "일판": "JP",\n        "US": "US", "USA": "US", "EN": "US", "ENG": "US", "ENGLISH": "US",\n        "영문판": "US", "영판": "US", "미국판": "US",\n        "UNKNOWN": "UNKNOWN",\n    }\n    return aliases.get(region, "UNKNOWN")\n''','python normalize_region')
s=replace_once(s,
'''    explicit_patterns = (\n        ("KR", r"(?:\\b(?:KR|KOREA|KOREAN)\\b|한국판|한글판|국판)"),\n        ("JP", r"(?:\\b(?:JP|JAPAN|JAPANESE)\\b|日本版|日版)"),\n        ("US", r"(?:\\b(?:US|USA|EN|ENGLISH)\\b|영문판|미국판)"),\n    )\n    for region, pattern in explicit_patterns:\n        if re.search(pattern, upper, re.I):\n            signals.append({"region": region, "basis": "explicit_region_label", "confidence": 0.99})\n\n    hangul = len(re.findall(r"[가-힣]", text))\n    kana = len(re.findall(r"[ぁ-んァ-ヶー]", text))\n    if hangul >= 2:\n''',
'''    explicit_patterns = (\n        ("KR", r"(?:\\b(?:KR|KOR|KOREA|KOREAN)\\b|한국판|한글판|한판|국판)"),\n        ("JP", r"(?:\\b(?:JP|JPN|JAPAN|JAPANESE)\\b|日本版|日版|일본판|일판)"),\n        ("US", r"(?:\\b(?:US|USA|EN|ENG|ENGLISH)\\b|영문판|영판|미국판)"),\n    )\n    for region, pattern in explicit_patterns:\n        if re.search(pattern, upper, re.I):\n            signals.append({"region": region, "basis": "explicit_region_label", "confidence": 0.99})\n\n    # Collector-facing Korean labels describe metadata; their Hangul characters\n    # must not create a fake KR signal. Independent kana/set-code evidence still\n    # participates and can force a real cross-edition conflict.\n    suppress_hangul = bool(re.search(r"(?:일본판|일판|영문판|영판|미국판)", text, re.I))\n    hangul = len(re.findall(r"[가-힣]", text))\n    kana = len(re.findall(r"[ぁ-んァ-ヶー]", text))\n    if hangul >= 2 and not suppress_hangul:\n''','python edition aliases')
write(p,s)

p='card_identity_recognition.js'
s=read(p)
s=replace_once(s,
"function normalizeRegion(value){const r=generationText(value).replace(/\\s+/g,'');if(['JP','JAPAN','JAPANESE','日本','日版','日本版'].includes(r))return 'JP';if(['US','USA','EN','ENGLISH','영문판','미국판'].includes(r))return 'US';if(['KR','KOREA','KOREAN','한국','한국판','한글판'].includes(r))return 'KR';return 'UNKNOWN'}",
"function normalizeRegion(value){const r=generationText(value).replace(/\\s+/g,'');if(['JP','JPN','JAPAN','JAPANESE','日本','日版','日本版','일본판','일판'].includes(r))return 'JP';if(['US','USA','EN','ENG','ENGLISH','영문판','영판','미국판'].includes(r))return 'US';if(['KR','KOR','KOREA','KOREAN','한국','한국판','한글판','한판','국판'].includes(r))return 'KR';return 'UNKNOWN'}",
'js normalizeRegion')
s=replace_once(s,
''' if(/(?:\\b(?:KR|KOREA|KOREAN)\\b|한국판|한글판|국판)/i.test(upper))add('KR','explicit_region_label',.99);\n if(/(?:\\b(?:JP|JAPAN|JAPANESE)\\b|日本版|日版)/i.test(upper))add('JP','explicit_region_label',.99);\n if(/(?:\\b(?:US|USA|EN|ENGLISH)\\b|영문판|미국판)/i.test(upper))add('US','explicit_region_label',.99);\n const hangul=(raw.match(/[가-힣]/g)||[]).length,kana=(raw.match(/[ぁ-んァ-ヶー]/g)||[]).length;\n if(hangul>=2)add('KR','hangul_script',.96,{count:hangul});\n''',
''' if(/(?:\\b(?:KR|KOR|KOREA|KOREAN)\\b|한국판|한글판|한판|국판)/i.test(upper))add('KR','explicit_region_label',.99);\n if(/(?:\\b(?:JP|JPN|JAPAN|JAPANESE)\\b|日本版|日版|일본판|일판)/i.test(upper))add('JP','explicit_region_label',.99);\n if(/(?:\\b(?:US|USA|EN|ENG|ENGLISH)\\b|영문판|영판|미국판)/i.test(upper))add('US','explicit_region_label',.99);\n const suppressHangul=/(?:일본판|일판|영문판|영판|미국판)/i.test(raw);\n const hangul=(raw.match(/[가-힣]/g)||[]).length,kana=(raw.match(/[ぁ-んァ-ヶー]/g)||[]).length;\n if(hangul>=2&&!suppressHangul)add('KR','hangul_script',.96,{count:hangul});\n''','js edition aliases')
write(p,s)

# Touch service worker source so installed tablets see a new SW byte stream and\n# refresh the already network-first identity runtime without changing cache ABI.\np='sw.js'; s=read(p)
s=replace_once(s,
'// v276 rotates the tablet/PWA runtime cache so the latest navigation UI is pre-cached after upgrade.\n',
'// v324 refreshes tablet/PWA identity runtime while preserving the v276 cache ABI.\n',
'service worker refresh')
write(p,s)

test='''from __future__ import annotations\n\nimport json\nimport subprocess\nimport unittest\nfrom pathlib import Path\n\nimport card_identity_recognition as identity\n\nROOT=Path(__file__).resolve().parent\n\nclass CardCollectorEditionAliasV324Tests(unittest.TestCase):\n    def test_server_alias_normalization(self):\n        expected={\n            "한판":"KR","한국판":"KR","KOR":"KR",\n            "일판":"JP","일본판":"JP","JPN":"JP",\n            "영판":"US","영문판":"US","ENG":"US","EN":"US",\n        }\n        for raw,region in expected.items():\n            with self.subTest(raw=raw): self.assertEqual(region,identity.normalize_region(raw))\n\n    def test_collector_labels_do_not_self_conflict(self):\n        for text,region in (("한판 피카츄","KR"),("일판 Pikachu","JP"),("일본판 피카츄","JP"),("영판 피카츄","US"),("영문판 Pikachu","US")):\n            with self.subTest(text=text):\n                row=identity.infer_region_evidence(text)\n                self.assertEqual(region,row["region"])\n                self.assertFalse(row["conflict"])\n                self.assertIn("explicit_region_label",row["basis"])\n\n    def test_independent_evidence_still_conflicts(self):\n        row=identity.infer_region_evidence("일본판 Pikachu PAL185/193")\n        self.assertEqual("UNKNOWN",row["region"])\n        self.assertTrue(row["conflict"])\n        self.assertEqual({"JP","US"},{item["region"] for item in row["signals"]})\n\n    def browser(self,text):\n        script=r'''\nconst fs=require('fs'),vm=require('vm');\nglobal.window={};global.document={readyState:'loading',addEventListener(){},getElementById(){return null;}};\nglobal.localStorage={getItem(){return null;},setItem(){}};global.Option=function(){};\nvm.runInThisContext(fs.readFileSync('card_identity_recognition.js','utf8'));\nprocess.stdout.write(JSON.stringify(global.window.TCGPokemonGeneration.inferRegion(process.argv[1])));\n'''\n        p=subprocess.run(["node","-e",script,text],cwd=ROOT,text=True,capture_output=True,timeout=30,check=False)\n        self.assertEqual(0,p.returncode,p.stdout+p.stderr)\n        return json.loads(p.stdout)\n\n    def test_browser_server_parity(self):\n        for text,region in (("한판 Pikachu","KR"),("일판 피카츄","JP"),("영판 Pikachu","US")):\n            with self.subTest(text=text):\n                self.assertEqual(region,self.browser(text)["region"])\n\n    def test_browser_keeps_real_conflict_fail_closed(self):\n        row=self.browser("일본판 Pikachu PAL185/193")\n        self.assertEqual("UNKNOWN",row["region"]); self.assertTrue(row["conflict"])\n\n    def test_service_worker_refreshes_identity_runtime(self):\n        sw=(ROOT/"sw.js").read_text(encoding="utf-8")\n        self.assertIn("v324 refreshes tablet/PWA identity runtime",sw)\n        self.assertIn("'./card_identity_recognition.js'",sw)\n\nif __name__=='__main__': unittest.main(verbosity=2)\n'''
write('test_card_collector_edition_alias_v324.py',test)

p='verify_current_runtime.py'; s=read(p)
needle='"test_card_variant_market_precision_v323.py","test_multi_market_price_collector.py"'
count=s.count(needle)
if count<1: raise SystemExit(f'verify_current_runtime anchor missing: {count}')
s=s.replace(needle,'"test_card_variant_market_precision_v323.py","test_card_collector_edition_alias_v324.py","test_multi_market_price_collector.py"')
write(p,s)
print('v324 patch applied')

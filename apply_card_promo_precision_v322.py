#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def patch(path, old, new, label):
    p=ROOT/path
    text=p.read_text(encoding='utf-8')
    count=text.count(old)
    if count!=1:
        raise SystemExit(f'{label}: expected 1 match, got {count}')
    p.write_text(text.replace(old,new,1),encoding='utf-8')


# Python identity OCR: normalize shared JP/KR promo families and modern EN promo IDs.
patch('card_identity_recognition.py',
'''_POKEMON_EN_SET_PATTERN = "|".join(map(re.escape, POKEMON_EN_SET_CODES))
_POKEMON_EN_SET_EVIDENCE_RE = re.compile(
    rf"(?<![A-Z0-9])(?:{_POKEMON_EN_SET_PATTERN})\\s*[- ]?\\s*\\d{{1,3}}(?:\\s*/\\s*\\d{{2,3}})?(?![A-Z0-9])",
    re.I,
)''',
'''_POKEMON_EN_SET_PATTERN = "|".join(map(re.escape, POKEMON_EN_SET_CODES))
_POKEMON_EN_SET_EVIDENCE_RE = re.compile(
    rf"(?<![A-Z0-9])(?:{_POKEMON_EN_SET_PATTERN})\\s*[- ]?\\s*\\d{{1,3}}(?:\\s*/\\s*\\d{{2,3}})?(?![A-Z0-9])",
    re.I,
)
_POKEMON_EN_PROMO_EVIDENCE_RE = re.compile(
    r"(?<![A-Z0-9])(?:SWSH|SVP|MEP)\\s*-?\\s*\\d{1,3}(?![A-Z0-9])", re.I
)
_SHARED_PROMO_CODE_PATTERN = r"(?:SV-P|S-P|SM-P|XY-P|BW-P|DP-P|M-P)"''',
'promo constants')

patch('card_identity_recognition.py',
'''NUMBER_RE = re.compile(
    r"(?<![A-Z0-9])(?:\\d{1,3}/\\d{2,3}|(?:MEG|PFL|ASC|POR|CRI|PBL|SVI|PAL|OBF|MEW|PAR|PAF|TEF|TWM|SFA|SCR|SSP|PRE|JTG|DRI|BLK|WHT|OP|ST|EB|PRB|P|CP|FB|SV|SM|S)\\s*-?\\s*\\d{1,3}(?:-\\d{2,3})?)(?![A-Z0-9])",
    re.I,
)''',
'''NUMBER_RE = re.compile(
    r"(?<![A-Z0-9])(?:"
    r"\\d{1,3}/(?:SV-P|S-P|SM-P|XY-P|BW-P|DP-P|M-P)"
    r"|(?:SV-P|S-P|SM-P|XY-P|BW-P|DP-P|M-P)\\s*\\d{1,3}"
    r"|(?:SWSH|SVP|MEP)\\s*-?\\s*\\d{1,3}"
    r"|\\d{1,3}/\\d{2,3}"
    r"|(?:MEG|PFL|ASC|POR|CRI|PBL|SVI|PAL|OBF|MEW|PAR|PAF|TEF|TWM|SFA|SCR|SSP|PRE|JTG|DRI|BLK|WHT|OP|ST|EB|PRB|P|CP|FB|SV|SM|S)\\s*-?\\s*\\d{1,3}(?:-\\d{2,3})?"
    r")(?![A-Z0-9])",
    re.I,
)''',
'identity promo number regex')

patch('card_identity_recognition.py',
'''def normalize_number(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).upper().strip()
    text = re.sub(r"\\s+", "", text).replace("—", "-").replace("–", "-")
    if not text or len(text) > 32 or not re.fullmatch(r"[A-Z0-9./-]+", text):
        return ""
    return text''',
'''def normalize_number(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).upper().strip()
    text = re.sub(r"\\s+", "", text).replace("—", "-").replace("–", "-")
    if not text or len(text) > 32 or not re.fullmatch(r"[A-Z0-9./-]+", text):
        return ""
    suffix = re.fullmatch(r"(\\d{1,3})/(SV-P|S-P|SM-P|XY-P|BW-P|DP-P|M-P)", text)
    if suffix:
        return f"{suffix.group(2)}{int(suffix.group(1)):03d}"
    prefix = re.fullmatch(r"(SV-P|S-P|SM-P|XY-P|BW-P|DP-P|M-P)-?(\\d{1,3})", text)
    if prefix:
        return f"{prefix.group(1)}{int(prefix.group(2)):03d}"
    english = re.fullmatch(r"(SWSH|SVP|MEP)-?(\\d{1,3})", text)
    if english:
        return f"{english.group(1)}{int(english.group(2)):03d}"
    return text''',
'identity promo number normalization')

patch('card_identity_recognition.py',
'''    if _POKEMON_EN_SET_EVIDENCE_RE.search(upper):
        signals.append({"region": "US", "basis": "english_set_code", "confidence": 0.92})''',
'''    if _POKEMON_EN_SET_EVIDENCE_RE.search(upper):
        signals.append({"region": "US", "basis": "english_set_code", "confidence": 0.92})
    if _POKEMON_EN_PROMO_EVIDENCE_RE.search(upper):
        signals.append({"region": "US", "basis": "english_promo_code", "confidence": 0.94})''',
'english promo edition evidence')

# Browser generation: recognize promo families without inventing KR vs JP from shared codes.
patch('card_identity_recognition.js',
'''const EN_SET_CODES=new Set([...EN_SV_CODES,...EN_MEGA_CODES]);''',
'''const EN_SET_CODES=new Set([...EN_SV_CODES,...EN_MEGA_CODES]);
const EN_PROMO_CODES=new Set(['SWSH','SVP','MEP']);
const SHARED_PROMO_CODES=new Set(['SV-P','S-P','SM-P','XY-P','BW-P','DP-P','M-P']);''',
'browser promo constants')

patch('card_identity_recognition.js',
''' const englishSet=upper.match(new RegExp(`(?:^|[^A-Z0-9])(${[...EN_SET_CODES].join('|')})\\\\s*[- ]?\\\\s*\\\\d{1,3}(?:\\\\s*/\\\\s*\\\\d{2,3})?(?=[^A-Z0-9]|$)`));
 if(englishSet)add('US',`english_set_code_${englishSet[1]}`,.92);''',
''' const englishSet=upper.match(new RegExp(`(?:^|[^A-Z0-9])(${[...EN_SET_CODES].join('|')})\\\\s*[- ]?\\\\s*\\\\d{1,3}(?:\\\\s*/\\\\s*\\\\d{2,3})?(?=[^A-Z0-9]|$)`));
 if(englishSet)add('US',`english_set_code_${englishSet[1]}`,.92);
 const englishPromo=upper.match(/(?:^|[^A-Z0-9])(SWSH|SVP|MEP)\\s*-?\\s*\\d{1,3}(?=[^A-Z0-9]|$)/);
 if(englishPromo)add('US',`english_promo_code_${englishPromo[1]}`,.94);''',
'browser english promo edition evidence')

patch('card_identity_recognition.js',
''' const n=generationText(value).replace(/\\s+/g,'');
 let m;
 if((m=n.match(new RegExp(`^(${[...EN_SET_CODES].join('|')})(?=\\\\d|[-/])`))))return m[1];''',
''' const n=generationText(value).replace(/\\s+/g,'');
 let m;
 if((m=n.match(/^(\\d{1,3})\\/(SV-P|S-P|SM-P|XY-P|BW-P|DP-P|M-P)$/)))return m[2];
 if((m=n.match(/^(SV-P|S-P|SM-P|XY-P|BW-P|DP-P|M-P)-?\\d{1,3}$/)))return m[1];
 if((m=n.match(/^(SWSH|SVP|MEP)-?\\d{1,3}$/)))return m[1];
 if((m=n.match(new RegExp(`^(${[...EN_SET_CODES].join('|')})(?=\\\\d|[-/])`))))return m[1];''',
'browser promo card-number expansion')

patch('card_identity_recognition.js',
''' const t=generationText(text),patterns=[
  new RegExp(`(?:^|[^A-Z0-9])(${[...EN_SET_CODES].join('|')})\\\\s*[- ]?\\\\s*\\\\d{1,3}(?:\\\\s*/\\\\s*\\\\d{2,3})?(?=[^A-Z0-9]|$)`),''',
''' const t=generationText(text),patterns=[
  /(?:^|[^A-Z0-9])\\d{1,3}\\s*\\/\\s*(SV-P|S-P|SM-P|XY-P|BW-P|DP-P|M-P)(?=[^A-Z0-9]|$)/,
  /(?:^|[^A-Z0-9])(SV-P|S-P|SM-P|XY-P|BW-P|DP-P|M-P)\\s*\\d{1,3}(?=[^A-Z0-9]|$)/,
  /(?:^|[^A-Z0-9])(SWSH|SVP|MEP)\\s*-?\\s*\\d{1,3}(?=[^A-Z0-9]|$)/,
  new RegExp(`(?:^|[^A-Z0-9])(${[...EN_SET_CODES].join('|')})\\\\s*[- ]?\\\\s*\\\\d{1,3}(?:\\\\s*/\\\\s*\\\\d{2,3})?(?=[^A-Z0-9]|$)`),''',
'browser promo OCR expansion')

patch('card_identity_recognition.js',
'''function generationBySetCode(code){
 const c=generationText(code).replace(/\\s+/g,'');
 if(EN_MEGA_CODES.has(c))return {generation:null,generation_label:'세대 단정 안 함',series:'MEGA Evolution 시리즈',era:'MEGA',set_region:'US'};''',
'''function generationBySetCode(code){
 const c=generationText(code).replace(/\\s+/g,'');
 if(c==='M-P'||c==='MEP')return {generation:null,generation_label:'세대 단정 안 함',series:'MEGA 프로모',era:'MEGA',...(c==='MEP'?{set_region:'US'}:{})};
 if(c==='SV-P'||c==='SVP')return {generation:9,generation_label:'9세대',series:'스칼렛&바이올렛 프로모',era:'SV',...(c==='SVP'?{set_region:'US'}:{})};
 if(c==='S-P'||c==='SWSH')return {generation:8,generation_label:'8세대',series:'소드&실드 프로모',era:'S',...(c==='SWSH'?{set_region:'US'}:{})};
 if(c==='SM-P')return {generation:7,generation_label:'7세대',series:'썬&문 프로모',era:'SM'};
 if(c==='XY-P')return {generation:6,generation_label:'6세대',series:'XY 프로모',era:'XY'};
 if(c==='BW-P')return {generation:5,generation_label:'5세대',series:'BW 프로모',era:'BW'};
 if(c==='DP-P')return {generation:4,generation_label:'4세대',series:'DP 프로모',era:'DP'};
 if(EN_MEGA_CODES.has(c))return {generation:null,generation_label:'세대 단정 안 함',series:'MEGA Evolution 시리즈',era:'MEGA',set_region:'US'};''',
'browser promo generation mapping')

# Exact-card market identity must canonicalize the same promo code family.
patch('multi_market_price_collector.py',
'''def _normalize_card_number(value):
    """Canonicalize a card number without turning substring overlap into identity."""
    text=str(value or '').upper().strip().replace('–','-').replace('—','-')
    text=re.sub(r'\\s+','',text)
    return re.sub(r'[^A-Z0-9/-]','',text)''',
'''def _normalize_card_number(value):
    """Canonicalize a card number without turning substring overlap into identity."""
    text=str(value or '').upper().strip().replace('–','-').replace('—','-')
    text=re.sub(r'\\s+','',text)
    text=re.sub(r'[^A-Z0-9/-]','',text)
    suffix=re.fullmatch(r'(\\d{1,3})/(SV-P|S-P|SM-P|XY-P|BW-P|DP-P|M-P)',text)
    if suffix:return f"{suffix.group(2)}{int(suffix.group(1)):03d}"
    prefix=re.fullmatch(r'(SV-P|S-P|SM-P|XY-P|BW-P|DP-P|M-P)-?(\\d{1,3})',text)
    if prefix:return f"{prefix.group(1)}{int(prefix.group(2)):03d}"
    english=re.fullmatch(r'(SWSH|SVP|MEP)-?(\\d{1,3})',text)
    if english:return f"{english.group(1)}{int(english.group(2)):03d}"
    return text''',
'market promo normalization')

patch('multi_market_price_collector.py',
'''CARD_NUMBER_QUERY_RE=re.compile(
    r'(?<![A-Z0-9])(?:'
    r'(?:SVI|PAL|OBF|MEW|PAR|PAF|TEF|TWM|SFA|SCR|SSP|PRE|JTG|DRI|BLK|WHT|MEG|PFL|ASC|POR|CRI|PBL)\\s*-?\\s*\\d{1,4}(?:/\\d{2,4})?'
    r'|[A-Z]{1,4}\\d{1,3}[A-Z]{0,2}-?\\d{1,4}(?:/\\d{2,4})?'
    r'|\\d{1,4}/\\d{2,4}'
    r'|\\d{1,4}'
    r')(?![A-Z0-9])',re.I
)''',
'''CARD_NUMBER_QUERY_RE=re.compile(
    r'(?<![A-Z0-9])(?:'
    r'\\d{1,3}/(?:SV-P|S-P|SM-P|XY-P|BW-P|DP-P|M-P)'
    r'|(?:SV-P|S-P|SM-P|XY-P|BW-P|DP-P|M-P)\\s*\\d{1,3}'
    r'|(?:SWSH|SVP|MEP)\\s*-?\\s*\\d{1,3}'
    r'|(?:SVI|PAL|OBF|MEW|PAR|PAF|TEF|TWM|SFA|SCR|SSP|PRE|JTG|DRI|BLK|WHT|MEG|PFL|ASC|POR|CRI|PBL)\\s*-?\\s*\\d{1,4}(?:/\\d{2,4})?'
    r'|[A-Z]{1,4}\\d{1,3}[A-Z]{0,2}-?\\d{1,4}(?:/\\d{2,4})?'
    r'|\\d{1,4}/\\d{2,4}'
    r'|\\d{1,4}'
    r')(?![A-Z0-9])',re.I
)''',
'market promo query regex')

# Runtime gate should continuously execute the new promo-format regressions.
patch('verify_current_runtime.py',
'''       "test_card_identity_ambiguity_v320.py","test_card_precision_v321.py","test_multi_market_price_collector.py","test_tablet_runtime_manifest_ui_assets_v254.py"],360,False),''',
'''       "test_card_identity_ambiguity_v320.py","test_card_precision_v321.py","test_card_promo_precision_v322.py","test_multi_market_price_collector.py","test_tablet_runtime_manifest_ui_assets_v254.py"],360,False),''',
'current runtime v322 test')
patch('verify_current_runtime.py',
'''payload={"schema_version":1,"engine":"current-main-v321-edition-consensus-valuation-provenance"''',
'''payload={"schema_version":1,"engine":"current-main-v322-promo-identity-generation-market-precision"''',
'current runtime v322 engine')

(ROOT/'test_card_promo_precision_v322.py').write_text(r'''from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

import card_identity_recognition as identity
import multi_market_price_collector as market

ROOT=Path(__file__).resolve().parent


class CardPromoPrecisionV322Tests(unittest.TestCase):
    def _infer(self,payload):
        script=r"""
const fs=require('fs'),vm=require('vm');
global.window={};
global.document={readyState:'loading',addEventListener(){},getElementById(){return null;}};
global.localStorage={getItem(){return null;},setItem(){}};
global.Option=function(){};
vm.runInThisContext(fs.readFileSync('card_identity_recognition.js','utf8'));
process.stdout.write(JSON.stringify(global.window.TCGPokemonGeneration.infer(JSON.parse(process.argv[1]))));
"""
        proc=subprocess.run(['node','-e',script,json.dumps(payload)],cwd=ROOT,text=True,capture_output=True,check=True,timeout=30)
        return json.loads(proc.stdout)

    def test_shared_jp_kr_promo_numbers_are_canonical(self):
        pairs={
            '057/SV-P':'SV-P057','SV-P 57':'SV-P057','141/S-P':'S-P141',
            '301/SM-P':'SM-P301','108/XY-P':'XY-P108','190/BW-P':'BW-P190',
            '085/M-P':'M-P085',
        }
        for raw,expected in pairs.items():
            with self.subTest(raw=raw):
                self.assertEqual(expected,identity.normalize_number(raw))
                self.assertEqual(expected,market._normalize_card_number(raw))

    def test_modern_english_promo_numbers_are_canonical_and_english_evidence(self):
        for raw,expected in {'SWSH146':'SWSH146','SVP 034':'SVP034','MEP085':'MEP085'}.items():
            with self.subTest(raw=raw):
                self.assertEqual(expected,identity.normalize_number(raw))
                self.assertEqual(expected,market._normalize_card_number(raw))
                evidence=identity.infer_region_evidence(raw)
                self.assertEqual('US',evidence['region'])
                self.assertIn('english_promo_code',evidence['basis'])
        self.assertEqual('UNKNOWN',identity.infer_region_evidence('141/S-P')['region'])

    def test_identity_ocr_extracts_promo_numbers_without_losing_family(self):
        text='cards 057/SV-P 141/S-P 301/SM-P 108/XY-P 190/BW-P 085/M-P SWSH146 SVP034 MEP085'
        found=set(identity.extract_numbers(text))
        for expected in {'SV-P057','S-P141','SM-P301','XY-P108','BW-P190','M-P085','SWSH146','SVP034','MEP085'}:
            self.assertIn(expected,found)

    def test_generation_mapping_for_shared_promo_families(self):
        cases=[
            ('057/SV-P','JP',9,'SV'),('141/S-P','KR',8,'S'),('301/SM-P','JP',7,'SM'),
            ('108/XY-P','JP',6,'XY'),('190/BW-P','JP',5,'BW'),
        ]
        for number,region,generation,era in cases:
            with self.subTest(number=number,region=region):
                row=self._infer({'game':'pokemon','card_number':number,'region':region})
                self.assertEqual('estimated',row['status'])
                self.assertEqual(generation,row['generation'])
                self.assertEqual(era,row['era'])
        mega=self._infer({'game':'pokemon','card_number':'085/M-P','region':'JP'})
        self.assertEqual('estimated',mega['status'])
        self.assertIsNone(mega['generation'])
        self.assertEqual('MEGA',mega['era'])

    def test_generation_mapping_for_english_promos(self):
        for number,generation,era in [('SWSH146',8,'S'),('SVP034',9,'SV')]:
            with self.subTest(number=number):
                row=self._infer({'game':'pokemon','card_number':number,'region':'US'})
                self.assertEqual(generation,row['generation'])
                self.assertEqual(era,row['era'])
        mega=self._infer({'game':'pokemon','card_number':'MEP085','region':'US'})
        self.assertIsNone(mega['generation'])
        self.assertEqual('MEGA',mega['era'])

    def test_market_query_and_listing_use_same_promo_identity(self):
        for query,listing,expected in [
            ('Pikachu 141/S-P Korean','Pikachu S-P141 sold','S-P141'),
            ('Pikachu SVP034 English','Pikachu SVP 034 sold','SVP034'),
            ('Pikachu SWSH146 English','Pikachu SWSH146 sold','SWSH146'),
        ]:
            with self.subTest(query=query):
                name,number=market._tcgdex_query_parts(query)
                self.assertEqual(expected,market._normalize_card_number(number))
                self.assertTrue(market._card_number_matches(number,listing.split()[1]+' '+(listing.split()[2] if listing.split()[1]=='SVP' else '')) if listing.split()[1]=='SVP' else market._card_number_matches(number,listing.split()[1]))


if __name__=='__main__':
    unittest.main(verbosity=2)
''',encoding='utf-8')

print('v322 promo precision patch applied')

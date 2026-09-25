from pathlib import Path
import re


def replace_between(path, start_marker, end_marker, replacement):
    p=Path(path); text=p.read_text(encoding='utf-8')
    start=text.index(start_marker); end=text.index(end_marker,start)
    text=text[:start]+replacement.rstrip()+"\n\n"+text[end:]
    p.write_text(text,encoding='utf-8')


def replace_once(path, old, new):
    p=Path(path); text=p.read_text(encoding='utf-8')
    if text.count(old)!=1:
        raise RuntimeError(f'{path}: expected one match, got {text.count(old)} for {old[:80]!r}')
    p.write_text(text.replace(old,new,1),encoding='utf-8')


# --- Server OCR / edition evidence: preserve fail-closed learning, expose richer evidence. ---
replace_between(
    'card_identity_recognition.py',
    'def infer_region_from_text(value: Any) -> str:',
    'def _json(path: Path, fallback: dict) -> dict:',
    r'''def infer_region_evidence(value: Any) -> dict[str, Any]:
    """Return bounded KR/JP/US evidence and fail closed when strong signals disagree."""
    text = unicodedata.normalize("NFKC", str(value or ""))[:MAX_OCR_TEXT]
    upper = text.upper()
    signals: list[dict[str, Any]] = []

    explicit_patterns = (
        ("KR", r"(?:\b(?:KR|KOREA|KOREAN)\b|한국판|한글판|국판)"),
        ("JP", r"(?:\b(?:JP|JAPAN|JAPANESE)\b|日本版|日版)"),
        ("US", r"(?:\b(?:US|USA|ENGLISH)\b|영문판|미국판)"),
    )
    for region, pattern in explicit_patterns:
        if re.search(pattern, upper, re.I):
            signals.append({"region": region, "basis": "explicit_region_label", "confidence": 0.99})

    hangul = len(re.findall(r"[가-힣]", text))
    kana = len(re.findall(r"[ぁ-んァ-ヶー]", text))
    if hangul >= 2:
        signals.append({"region": "KR", "basis": "hangul_script", "confidence": 0.96, "count": hangul})
    if kana >= 2:
        signals.append({"region": "JP", "basis": "kana_script", "confidence": 0.96, "count": kana})
    if _POKEMON_EN_SET_EVIDENCE_RE.search(upper):
        signals.append({"region": "US", "basis": "english_set_code", "confidence": 0.92})

    regions = sorted({str(item["region"]) for item in signals})
    if len(regions) > 1:
        return {
            "region": "UNKNOWN", "confidence": 0.0, "basis": "edition_evidence_conflict",
            "conflict": True, "signals": signals,
        }
    if not regions:
        return {
            "region": "UNKNOWN", "confidence": 0.0, "basis": "insufficient_evidence",
            "conflict": False, "signals": [],
        }
    region = regions[0]
    matching = [item for item in signals if item["region"] == region]
    return {
        "region": region,
        "confidence": round(max(float(item["confidence"]) for item in matching), 3),
        "basis": "+".join(dict.fromkeys(str(item["basis"]) for item in matching)),
        "conflict": False,
        "signals": matching,
    }


def infer_region_from_text(value: Any) -> str:
    """Compatibility wrapper for callers that only need the edition code."""
    return str(infer_region_evidence(value).get("region") or "UNKNOWN")
'''
)

replace_once(
    'card_identity_recognition.py',
    '''    inferred_region = infer_region_from_text(supplied_text)\n    region_conflict = (\n        region in {"KR", "JP", "US"}\n        and inferred_region in {"KR", "JP", "US"}\n        and inferred_region != region\n    )''',
    '''    region_evidence = infer_region_evidence(supplied_text)\n    inferred_region = str(region_evidence.get("region") or "UNKNOWN")\n    region_conflict = bool(region_evidence.get("conflict")) or (\n        region in {"KR", "JP", "US"}\n        and inferred_region in {"KR", "JP", "US"}\n        and inferred_region != region\n    )'''
)
replace_once(
    'card_identity_recognition.py',
    '''        "ok": True, "game": game, "region_hint": region, "inferred_region": inferred_region,\n        "region_conflict": region_conflict, "image_hash": image_hash, "ocr_text": supplied_text,''',
    '''        "ok": True, "game": game, "region_hint": region, "inferred_region": inferred_region,\n        "region_conflict": region_conflict, "region_evidence": region_evidence,\n        "image_hash": image_hash, "ocr_text": supplied_text,'''
)

# --- Browser edition + Pokémon generation: cross-check independent evidence, do not invent. ---
replace_between(
    'card_identity_recognition.js',
    'function inferEditionFromText(value){',
    'function expansionFromCardNumber(value){',
    r'''function inferEditionFromText(value){
 const raw=String(value??'').normalize?.('NFKC')||String(value??''),upper=generationText(raw),signals=[];
 const add=(region,basis,confidence,extra={})=>signals.push({region,basis,confidence,...extra});
 if(/(?:\b(?:KR|KOREA|KOREAN)\b|한국판|한글판|국판)/i.test(upper))add('KR','explicit_region_label',.99);
 if(/(?:\b(?:JP|JAPAN|JAPANESE)\b|日本版|日版)/i.test(upper))add('JP','explicit_region_label',.99);
 if(/(?:\b(?:US|USA|ENGLISH)\b|영문판|미국판)/i.test(upper))add('US','explicit_region_label',.99);
 const hangul=(raw.match(/[가-힣]/g)||[]).length,kana=(raw.match(/[ぁ-んァ-ヶー]/g)||[]).length;
 if(hangul>=2)add('KR','hangul_script',.96,{count:hangul});
 if(kana>=2)add('JP','kana_script',.96,{count:kana});
 const englishSet=upper.match(new RegExp(`(?:^|[^A-Z0-9])(${[...EN_SET_CODES].join('|')})\\s*[- ]?\\s*\\d{1,3}(?:\\s*/\\s*\\d{2,3})?(?=[^A-Z0-9]|$)`));
 if(englishSet)add('US',`english_set_code_${englishSet[1]}`,.92);
 const regions=[...new Set(signals.map(row=>row.region))].sort();
 if(regions.length>1)return {region:'UNKNOWN',confidence:0,basis:'edition_evidence_conflict',conflict:true,signals};
 if(!regions.length)return {region:'UNKNOWN',confidence:0,basis:'insufficient_evidence',conflict:false,signals:[]};
 const region=regions[0],matching=signals.filter(row=>row.region===region);
 return {region,confidence:Math.max(...matching.map(row=>row.confidence)),basis:[...new Set(matching.map(row=>row.basis))].join('+'),conflict:false,signals:matching};
}'''
)

# Insert era/year compatibility helper immediately before generationConflict.
replace_once(
    'card_identity_recognition.js',
    'function generationConflict(inputRegion,byExpansion,expansion,regulation,byReg){',
    r'''function generationYearRange(era){
 const ranges={DP:[2006,2011],BW:[2010,2014],XY:[2013,2017],SM:[2016,2020],S:[2019,2023],SV:[2022,2026],MEGA:[2025,2028],CURRENT:[2025,2028]};
 return ranges[era]||null;
}
function generationYearConflict(base,year,expansion,regulation){
 if(!base||!Number.isInteger(year))return null;
 const range=generationYearRange(base.era);if(!range||year>=range[0]&&year<=range[1])return null;
 return {status:'conflict',game:'pokemon',generation:null,generation_label:'근거 충돌',series:'세트/레귤레이션과 ©연도 재확인',era:'CONFLICT',expansion_code:expansion||'',regulation_mark:regulation||'',year,confidence:0,confidence_level:'conflict',basis:[base.era&&`시리즈 ${base.era}`,`©/제작연도 ${year}`].filter(Boolean),note:'세트·레귤레이션 시기와 OCR 연도가 넓은 허용범위 밖이라 세대를 단정하지 않았습니다.'};
}
function generationConflict(inputRegion,byExpansion,expansion,regulation,byReg){'''
)

replace_between(
    'card_identity_recognition.js',
    'function inferPokemonGeneration(input={}){',
    'function renderPokemonGeneration(info,game=',
    r'''function inferPokemonGeneration(input={}){
 const game=String(input.game||'pokemon').trim().toLowerCase();
 if(game!=='pokemon')return {status:'not_applicable',game,generation:null,confidence:0,basis:[]};
 const text=[input.ocr_text,input.card_name,input.market_key].map(generationText).filter(Boolean).join(' ');
 const inputRegion=normalizeRegion(input?.region),year=yearFromEvidence(input,text);
 const expansion=expansionFromCardNumber(input.card_number)||expansionFromOcr(text);
 const byExpansion=generationBySetCode(expansion);
 const regulation=regulationFromEvidence(input,text),byReg=generationByRegulation(regulation);
 const conflict=generationConflict(inputRegion,byExpansion,expansion,regulation,byReg);
 if(conflict){conflict.year=year;return conflict}
 if(byExpansion&&byReg&&byReg.era==='CURRENT'&&byExpansion.era!=='MEGA'){
  return {status:'conflict',game:'pokemon',generation:null,generation_label:'근거 충돌',series:'세트코드/레귤레이션 재확인',era:'CONFLICT',expansion_code:expansion||'',regulation_mark:regulation||'',year,confidence:0,confidence_level:'conflict',basis:[`세트코드 ${expansion}`,`레귤레이션 ${regulation}`],note:'현행 레귤레이션과 이전 시리즈 세트코드가 함께 검출되어 세대를 단정하지 않았습니다.'};
 }
 const timeConflict=generationYearConflict(byExpansion||byReg,year,expansion,regulation);
 if(timeConflict)return timeConflict;
 if(byExpansion){
  const basis=[`확장팩/세트 코드 ${expansion}`];
  if(byReg)basis.push(`레귤레이션 마크 ${regulation}`);
  if(year)basis.push(`©/제작연도 ${year}`);
  const evidence_count=basis.length;
  return {status:'estimated',game:'pokemon',...byExpansion,expansion_code:expansion,regulation_mark:regulation||'',year,confidence:evidence_count>=2?.995:.98,confidence_level:'high',evidence_count,basis,note:byExpansion.era==='MEGA'?'MEGA는 별도 TCG 시리즈/블록이므로 TCG 시리즈와 포켓몬 세대 번호를 분리해 표시합니다.':'확장팩/세트 코드와 독립 OCR 근거를 교차검증한 추정'};
 }
 if(byReg){
  const basis=[`레귤레이션 마크 ${regulation}`];if(year)basis.push(`©/제작연도 ${year}`);
  return {status:'estimated',game:'pokemon',...byReg,expansion_code:'',regulation_mark:regulation,year,confidence:year?.78:.72,confidence_level:'medium',evidence_count:basis.length,basis,note:'레귤레이션 마크는 대회 사용 가능성 표기이며 세대/시리즈는 보조 추정입니다.'};
 }
 const byYear=generationByYear(year,input?.region);
 if(byYear)return {status:'estimated',game:'pokemon',...byYear,expansion_code:'',regulation_mark:'',year,confidence:.58,confidence_level:'low',evidence_count:1,basis:[`©/제작연도 ${year}`],note:'연도만 확인되어 세대/시리즈는 보조 추정입니다.'};
 if(year&&year<2007)return {status:'legacy',game:'pokemon',generation:null,generation_label:'고전 카드',series:'초기~ADV/PCG 계열',era:'LEGACY',expansion_code:'',regulation_mark:'',year,confidence:.55,confidence_level:'low',evidence_count:1,basis:[`©/제작연도 ${year}`],note:'고전 카드는 확장팩 코드 확인 전 세대 번호를 단정하지 않습니다.'};
 return {status:'unknown',game:'pokemon',generation:null,generation_label:'세대 확인 필요',series:'확장팩 코드·레귤레이션·©연도 OCR 부족',era:'UNKNOWN',expansion_code:'',regulation_mark:'',year:null,confidence:0,confidence_level:'unknown',evidence_count:0,basis:[],note:'근거가 부족해 세대를 생성하지 않았습니다.'};
}
'''
)
replace_once('card_identity_recognition.js',"version:'v309'","version:'v315'")
replace_once('card_identity_recognition.js',"version:'v309-edition-isolated-ocr-learning'","version:'v315-evidence-isolated-confirmed-learning'")

# --- Market precision: exact grade labels + exact-card eligibility for headline/grade values. ---
replace_between(
    'multi_market_price_collector.py',
    'def _tcgdex_query_parts(query):',
    'def _tcgdex_api(query,game,fx,region=',
    r'''CARD_NUMBER_QUERY_RE=re.compile(r'\b(?:[A-Z]{1,6}\d{0,3}[- ]?)?[A-Z]?\d{1,4}(?:/[A-Z]?\d{1,4})?\b',re.I)
GRADER_QUERY_RE=re.compile(r'\b(?:PSA|BGS|CGC|TAG|BRG)\s*(?:10|[1-9])(?:\.5)?(?:\s*BLACK\s*LABEL)?\b',re.I)


def _query_card_number_match(query):
    text=str(query or '')
    for match in CARD_NUMBER_QUERY_RE.finditer(text):
        token=match.group(0).strip()
        prefix=text[max(0,match.start()-16):match.start()]
        if re.search(r'(?:PSA|BGS|CGC|TAG|BRG)\s*$',prefix,re.I):continue
        compact=_normalize_card_number(token)
        if compact.isdigit() and len(compact)==4 and 1996<=int(compact)<=2099:continue
        return match
    return None


def _tcgdex_query_parts(query):
    text=str(query or '').strip();match=_query_card_number_match(text);card_number=''
    if match:card_number=match.group(0).strip();name=(text[:match.start()]+' '+text[match.end():]).strip()
    else:name=text
    name=GRADER_QUERY_RE.sub(' ',name)
    name=re.sub(r'\b(?:pokemon|pok[eé]mon|card|tcg|korean|japanese|english|kr|jp|us|usa)\b',' ',name,flags=re.I)
    return re.sub(r'\s+',' ',name).strip(),card_number


def _identity_blob_numbers(value):
    text=str(value or '').upper().replace('–','-').replace('—','-')
    found=[]
    for match in CARD_NUMBER_QUERY_RE.finditer(text):
        token=_normalize_card_number(match.group(0))
        if token and token not in found:found.append(token)
    return found[:32]


def _identity_name_token(value):
    return re.sub(r'[^0-9a-z가-힣ぁ-んァ-ヶ一-龯]+','',str(value or '').casefold())[:160]


def _item_identity_eligibility(query,item):
    """Gate headline/grade prices on exact card-number evidence when one was requested."""
    wanted_name,wanted_number=_tcgdex_query_parts(query)
    if not wanted_number:return True,'name_only_query'
    wanted=_normalize_card_number(wanted_number)
    actual=_normalize_card_number(item.get('card_number'))
    title_blob=' '.join(str(item.get(key) or '') for key in ('title','snippet'))
    name_token=_identity_name_token(wanted_name)
    name_ok=bool(name_token and name_token in _identity_name_token(title_blob))
    if actual and _card_number_matches(wanted,actual):
        if _has_explicit_set_prefix(wanted) or name_ok:return True,'structured_card_number_exact'
        return False,'local_number_without_name_corroboration'
    candidates=_identity_blob_numbers(title_blob)
    if any(_card_number_matches(wanted,candidate) for candidate in candidates):
        if _has_explicit_set_prefix(wanted) or name_ok:return True,'text_card_number_exact'
        return False,'local_number_without_name_corroboration'
    return False,'card_number_mismatch'
'''
)

replace_between(
    'multi_market_price_collector.py',
    "GRADE_ORDER=('미감정'",
    'PRICE_EVIDENCE_PRIORITY=(',
    r'''PSA_GRADE_LABELS=tuple(f'PSA {grade}' for grade in range(10,0,-1))
GRADE_ORDER=('미감정',*PSA_GRADE_LABELS,'BGS 10 블랙라벨')


def _grade_number_label(company,value):
    try:number=float(value)
    except (TypeError,ValueError,OverflowError):return ''
    if not (1<=number<=10) or number*2!=int(number*2):return ''
    text=str(int(number)) if number.is_integer() else f'{number:.1f}'
    return f'{company} {text}'


def _grade_label(item):
    text=' '.join(str(item.get(k) or '') for k in ('title','snippet','price_kind'))
    if re.search(r'\bBGS\s*10(?:\.0)?\b[^\n]{0,28}\b(?:black\s*label|블랙\s*라벨)\b',text,re.I):return 'BGS 10 블랙라벨'
    for company in ('PSA','BGS','CGC','TAG','BRG'):
        match=re.search(rf'\b{company}\s*(10|[1-9])(?:\s*\.\s*(5))?\b',text,re.I)
        if match:
            value=float(match.group(1))+(.5 if match.group(2) else 0)
            label=_grade_number_label(company,value)
            if label:return label
    match=re.search(r'(?:등급|grade)\s*[:\-]?\s*([ABCD])\b',text,re.I)
    if match:return match.group(1).upper()
    return '미감정'


def _grade_sort_key(label):
    if label=='미감정':return (0,0,0)
    if label=='BGS 10 블랙라벨':return (2,-10.5,0)
    match=re.fullmatch(r'(PSA|BGS|CGC|TAG|BRG)\s+(10|[1-9])(?:\.(5))?',label)
    if match:
        company_order={'PSA':1,'BGS':2,'CGC':3,'TAG':4,'BRG':5}
        grade=float(match.group(2))+(.5 if match.group(3) else 0)
        return (company_order[match.group(1)],-grade,0)
    return (9,0,str(label))
'''
)

replace_between(
    'multi_market_price_collector.py',
    'def _grade_reference(items):',
    'def _query_grade_label(query):',
    r'''def _grade_reference(items):
    grouped={label:[] for label in GRADE_ORDER}
    for item in items:
        if int(item.get('price_krw') or 0)>0:
            grouped.setdefault(_grade_label(item),[]).append(item)
    labels=sorted(grouped,key=_grade_sort_key)
    rows=[]
    for label in labels:
        grade_items=grouped[label]
        chosen,basis,buckets=_select_price_evidence(grade_items)
        values=[int(item.get('price_krw') or 0) for item in chosen]
        rows.append({
            'grade':label,'count':len(values),'total_count':len(grade_items),'basis':basis,
            'completed_count':len(buckets['completed']),'api_reference_count':len(buckets['api_reference']),
            'asking_count':len(buckets['asking']),
            'price_krw':int(statistics.median(values)) if values else 0,
            'min_krw':min(values) if values else 0,'max_krw':max(values) if values else 0,
        })
    return rows
'''
)
replace_between(
    'multi_market_price_collector.py',
    'def _query_grade_label(query):',
    'def _comparable_summary_items(query,items):',
    r'''def _query_grade_label(query):
    label=_grade_label({'title':str(query or '')})
    return '' if label=='미감정' else label
'''
)

# Gate only headline and grade-reference calculations. Keep excluded rows visible as transparent references.
replace_once(
    'multi_market_price_collector.py',
    "    items=list(dedup.values());items.sort(key=lambda x:(-float(x.get('score',1)),-int(x.get('price_krw',0))))\n    comparable,basis=_comparable_summary_items(query,items)\n    prices=[int(x['price_krw']) for x in comparable if int(x.get('price_krw',0))>0]\n    summary={'count':len(prices),'total_count':len([x for x in items if int(x.get('price_krw',0))>0]),",
    "    items=list(dedup.values());items.sort(key=lambda x:(-float(x.get('score',1)),-int(x.get('price_krw',0))))\n    for item in items:\n        eligible,identity_basis=_item_identity_eligibility(query,item)\n        item['summary_eligible']=bool(eligible);item['identity_basis']=identity_basis\n    eligible_items=[item for item in items if item.get('summary_eligible') is True]\n    comparable,basis=_comparable_summary_items(query,eligible_items)\n    prices=[int(x['price_krw']) for x in comparable if int(x.get('price_krw',0))>0]\n    _,query_card_number=_tcgdex_query_parts(query)\n    summary={'count':len(prices),'total_count':len([x for x in eligible_items if int(x.get('price_krw',0))>0]),\n             'observed_total_count':len([x for x in items if int(x.get('price_krw',0))>0]),\n             'identity_excluded_count':len([x for x in items if x.get('summary_eligible') is False and int(x.get('price_krw',0))>0]),\n             'identity_scope':'exact_card_number' if query_card_number else 'name_only',"
)
replace_once(
    'multi_market_price_collector.py',
    "          'reference_links':_reference_links(query,game),'grade_reference':_grade_reference(items),\n          'notice':'SNKRDUNK·JustTCG·TCGdex·Pavilion을 포함한 공개 참고시세를 교차수집합니다. 단일 참고값은 공식 검증가격을 덮어쓰지 않으며, 등급값이 없으면 추정하지 않습니다. 403/429는 우회하지 않고 안전 대기합니다.',",
    "          'reference_links':_reference_links(query,game),'grade_reference':_grade_reference(eligible_items),\n          'notice':'SNKRDUNK·JustTCG·TCGdex·Pavilion을 포함한 공개 참고시세를 교차수집합니다. 카드번호가 있으면 정확 번호(+로컬번호는 카드명 확인)와 일치한 자료만 중앙값·등급별 시세에 사용합니다. 완료거래→API 참고시세→호가 순으로 분리하며, 없는 등급값은 추정하지 않습니다. 403/429는 우회하지 않고 안전 대기합니다.',"
)

# Front-end market details: label exact-card eligible rows and surface exclusions.
replace_once('multi_market_prices.js','version:313','version:315')
replace_once(
    'multi_market_prices.js',
    "function sourceBadge(item){\n return `<span class=\"mmp-source\">${esc(item.source)}</span><span class=\"mmp-kind\">${esc(item.price_kind||'가격')}</span>${item.verified_api?'<span class=\"mmp-api\">API</span>':''}`;\n}",
    "function sourceBadge(item){\n const identity=item.summary_eligible===false?'<span class=\"mmp-kind\">참고만</span>':(String(item.identity_basis||'').includes('card_number')?'<span class=\"mmp-api\">카드일치</span>':'');\n return `<span class=\"mmp-source\">${esc(item.source)}</span><span class=\"mmp-kind\">${esc(item.price_kind||'가격')}</span>${item.verified_api?'<span class=\"mmp-api\">API</span>':''}${identity}`;\n}"
)
replace_once(
    'multi_market_prices.js',
    "summary.innerHTML=`<div><span>비교가능가격</span><b>${info.count||0}건</b><small>전체 ${info.total_count??info.count??0}건</small></div>",
    "summary.innerHTML=`<div><span>비교가능가격</span><b>${info.count||0}건</b><small>정확범위 ${info.total_count??info.count??0}건${Number(info.identity_excluded_count)>0?` · 불일치 제외 ${Number(info.identity_excluded_count)}건`:''}</small></div>"
)
replace_once(
    'multi_market_prices.js',
    '완료거래를 우선하고, 없으면 API 참고시세·판매중/호가를 서로 섞지 않고 표시합니다.',
    '카드번호 일치 자료에서 업체·숫자등급을 분리하고, 완료거래→API 참고시세→판매중/호가 순으로 표시합니다.'
)

# --- Regression tests for evidence conflicts, exact grades and identity gating. ---
replace_once(
    'test_card_region_generation_precision_v306.py',
    "        self.assertEqual('UNKNOWN', identity.infer_region_from_text('Pikachu 25/102'))",
    "        self.assertEqual('UNKNOWN', identity.infer_region_from_text('Pikachu 25/102'))\n        self.assertEqual('JP', identity.infer_region_from_text('2026 Japanese Pokémon card Pikachu'))\n        evidence=identity.infer_region_evidence('Korean 포켓몬 ポケモン card')\n        self.assertEqual('UNKNOWN',evidence['region'])\n        self.assertTrue(evidence['conflict'])\n        self.assertGreaterEqual(len(evidence['signals']),2)"
)
replace_once(
    'test_card_region_generation_precision_v306.py',
    "        self.assertIn('Pokémon generation runtime v309: PASS',proc.stdout)",
    "        self.assertIn('Pokémon generation runtime v315: PASS',proc.stdout)"
)

replace_once(
    'verify_pokemon_generation_runtime.js',
    "region=api.inferRegion('Pikachu 25/102');eq(region.region,'UNKNOWN','generic Latin text must not invent edition');",
    "region=api.inferRegion('Pikachu 25/102');eq(region.region,'UNKNOWN','generic Latin text must not invent edition');\nregion=api.inferRegion('2026 Japanese Pokémon card Pikachu');eq(region.region,'JP','embedded Japanese label');ok(region.basis.includes('explicit_region_label'),'embedded label basis');"
)
replace_once(
    'verify_pokemon_generation_runtime.js',
    "region=api.inferRegion('포켓몬 카드 ポケモン カード');eq(region.region,'UNKNOWN','mixed strong scripts must not invent edition');eq(region.basis,'mixed_script_conflict','mixed script basis');",
    "region=api.inferRegion('포켓몬 카드 ポケモン カード');eq(region.region,'UNKNOWN','mixed strong scripts must not invent edition');eq(region.basis,'edition_evidence_conflict','mixed script basis');ok(region.conflict===true,'mixed script conflict flag');"
)
replace_once(
    'verify_pokemon_generation_runtime.js',
    "r=api.infer({game:'pokemon',card_number:'PAL185/193',region:'US',regulation_mark:'F'});\neq(r.status,'conflict','set generation vs regulation generation must conflict');eq(r.generation,null,'generation evidence conflict must fail closed');\n\neq(api.version,'v309','generation runtime version');\nconsole.log('Pokémon generation runtime v309: PASS');",
    "r=api.infer({game:'pokemon',card_number:'PAL185/193',region:'US',regulation_mark:'F'});\neq(r.status,'conflict','set generation vs regulation generation must conflict');eq(r.generation,null,'generation evidence conflict must fail closed');\n\nr=api.infer({game:'pokemon',card_number:'PAL185/193',region:'US',ocr_text:'©2020 Pokémon'});\neq(r.status,'conflict','set code vs impossible copyright year must conflict');eq(r.generation,null,'year conflict must fail closed');\n\nr=api.infer({game:'pokemon',card_number:'PAL185/193',region:'US',regulation_mark:'H',ocr_text:'©2024 Pokémon'});\neq(r.generation,9,'three-evidence generation');ok(r.evidence_count>=3,'three independent generation evidence');ok(r.basis.some(x=>x.includes('©/제작연도')),'year evidence retained');\n\neq(api.version,'v315','generation runtime version');\nconsole.log('Pokémon generation runtime v315: PASS');"
)

# Add detailed market tests before unittest runner.
p=Path('test_multi_market_price_collector.py');text=p.read_text(encoding='utf-8')
needle="\nif __name__=='__main__':\n    unittest.main()\n"
if needle not in text:raise RuntimeError('test runner marker missing')
addition=r'''
    def test_exact_numeric_grades_stay_separate_across_companies(self):
        items=[
            {'title':'Pikachu PSA 8 sold','price_kind':'실거래/완료 신호','price_krw':80000},
            {'title':'Pikachu PSA 7 sold','price_kind':'실거래/완료 신호','price_krw':70000},
            {'title':'Pikachu BGS 9.5 sold','price_kind':'실거래/완료 신호','price_krw':95000},
            {'title':'Pikachu CGC 10 sold','price_kind':'실거래/완료 신호','price_krw':110000},
            {'title':'Pikachu TAG 9 sold','price_kind':'실거래/완료 신호','price_krw':90000},
            {'title':'Pikachu BRG 8 sold','price_kind':'실거래/완료 신호','price_krw':81000},
        ]
        by_grade={row['grade']:row for row in m._grade_reference(items)}
        self.assertEqual(by_grade['PSA 8']['price_krw'],80000)
        self.assertEqual(by_grade['PSA 7']['price_krw'],70000)
        self.assertEqual(by_grade['BGS 9.5']['price_krw'],95000)
        self.assertEqual(by_grade['CGC 10']['price_krw'],110000)
        self.assertEqual(by_grade['TAG 9']['price_krw'],90000)
        self.assertEqual(by_grade['BRG 8']['price_krw'],81000)

    def test_grade_number_is_not_mistaken_for_card_number(self):
        name,number=m._tcgdex_query_parts('Pikachu PSA 10 English')
        self.assertEqual(number,'')
        self.assertEqual(name,'Pikachu')
        name,number=m._tcgdex_query_parts('Pikachu 025 PSA 10 English')
        self.assertEqual(m._normalize_card_number(number),'025')
        self.assertEqual(name,'Pikachu')

    def test_summary_identity_gate_rejects_wrong_card_number(self):
        good={'title':'Pikachu PAL 185/193 sold','snippet':'Pikachu','card_number':'PAL185/193','price_krw':100000}
        wrong={'title':'Pikachu PAL 186/193 sold','snippet':'Pikachu','card_number':'PAL186/193','price_krw':90000}
        self.assertEqual(m._item_identity_eligibility('Pikachu PAL185/193',good)[0],True)
        self.assertEqual(m._item_identity_eligibility('Pikachu PAL185/193',wrong)[0],False)
        local_good={'title':'Pikachu card 025 sold','snippet':'Pikachu','price_krw':50000}
        local_wrong_name={'title':'Raichu card 025 sold','snippet':'Raichu','price_krw':50000}
        self.assertTrue(m._item_identity_eligibility('Pikachu 025',local_good)[0])
        self.assertFalse(m._item_identity_eligibility('Pikachu 025',local_wrong_name)[0])
'''
text=text.replace(needle,'\n'+addition+needle,1);p.write_text(text,encoding='utf-8')

# Keep the legacy market-reference test aligned with exact PSA buckets.
replace_once(
    'test_market_reference_sources_v130.py',
    "        self.assertEqual(by_grade['PSA 9']['price_krw'],0)",
    "        self.assertEqual(by_grade['PSA 9']['price_krw'],0)\n        self.assertEqual(by_grade['PSA 8']['price_krw'],0)"
)

print('v315 card intelligence patch applied')

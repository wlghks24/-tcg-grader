from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def patch(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise SystemExit(f"{path}: expected marker missing: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# ---------------------------------------------------------------------------
# Identity: edition/language (KR/JP/EN) is distinct from market/catalog region
# (KR/JP/US). Keep the legacy region surface only for compatibility at the
# market boundary, and expose an explicit edition_language everywhere new code
# consumes identity evidence.
# ---------------------------------------------------------------------------
patch(
    "card_identity_recognition.py",
    'REGIONS = {"KR", "JP", "US", "UNKNOWN"}\n',
    'MARKET_REGIONS = {"KR", "JP", "US", "UNKNOWN"}\n'
    'EDITION_LANGUAGES = {"KR", "JP", "EN", "UNKNOWN"}\n'
    'REGIONS = MARKET_REGIONS  # legacy market/catalog compatibility only\n',
)

marker = '''def infer_region_evidence(value: Any) -> dict[str, Any]:\n    """Return bounded KR/JP/US evidence and fail closed when strong signals disagree."""\n'''
replacement = '''def normalize_edition_language(value: Any) -> str:\n    """Normalize a card edition/language independently from a sales market."""\n    token = unicodedata.normalize("NFKC", str(value or "")).strip().upper().replace(" ", "")\n    if token in {"KR", "KOR", "KOREA", "KOREAN", "한국", "한국판", "한글판", "한판", "국판"}:\n        return "KR"\n    if token in {"JP", "JPN", "JAPAN", "JAPANESE", "日本", "日本版", "日版", "일본판", "일판"}:\n        return "JP"\n    if token in {"EN", "ENG", "ENGLISH", "영문판", "영판", "US", "USA", "미국판"}:\n        return "EN"\n    return "UNKNOWN"\n\n\ndef market_region_for_edition(value: Any) -> str:\n    """Translate an edition/language to the legacy market/catalog region once."""\n    edition = normalize_edition_language(value)\n    return {"KR": "KR", "JP": "JP", "EN": "US"}.get(edition, "UNKNOWN")\n\n\ndef edition_language_for_market_region(value: Any) -> str:\n    """Translate a legacy market/catalog region to a card edition/language."""\n    region = normalize_region(value)\n    return {"KR": "KR", "JP": "JP", "US": "EN"}.get(region, "UNKNOWN")\n\n\ndef infer_region_evidence(value: Any) -> dict[str, Any]:\n    """Return fail-closed edition evidence with an explicit market boundary."""\n'''
patch("card_identity_recognition.py", marker, replacement)

old = '''    regions = sorted({str(item["region"]) for item in signals})\n    if len(regions) > 1:\n        return {\n            "region": "UNKNOWN", "confidence": 0.0, "basis": "edition_evidence_conflict",\n            "conflict": True, "signals": signals,\n        }\n    if not regions:\n        return {\n            "region": "UNKNOWN", "confidence": 0.0, "basis": "insufficient_evidence",\n            "conflict": False, "signals": [],\n        }\n    region = regions[0]\n    matching = [item for item in signals if item["region"] == region]\n    return {\n        "region": region,\n        "confidence": round(max(float(item["confidence"]) for item in matching), 3),\n        "basis": "+".join(dict.fromkeys(str(item["basis"]) for item in matching)),\n        "conflict": False,\n        "signals": matching,\n    }\n\n\ndef infer_region_from_text(value: Any) -> str:\n    """Compatibility wrapper for callers that only need the edition code."""\n    return str(infer_region_evidence(value).get("region") or "UNKNOWN")\n'''
new = '''    regions = sorted({str(item["region"]) for item in signals})\n    if len(regions) > 1:\n        return {\n            "region": "UNKNOWN", "market_region": "UNKNOWN", "edition_language": "UNKNOWN",\n            "confidence": 0.0, "basis": "edition_evidence_conflict",\n            "conflict": True, "signals": signals,\n        }\n    if not regions:\n        return {\n            "region": "UNKNOWN", "market_region": "UNKNOWN", "edition_language": "UNKNOWN",\n            "confidence": 0.0, "basis": "insufficient_evidence",\n            "conflict": False, "signals": [],\n        }\n    region = regions[0]\n    matching = [item for item in signals if item["region"] == region]\n    edition = edition_language_for_market_region(region)\n    return {\n        "region": region, "market_region": region, "edition_language": edition,\n        "confidence": round(max(float(item["confidence"]) for item in matching), 3),\n        "basis": "+".join(dict.fromkeys(str(item["basis"]) for item in matching)),\n        "conflict": False,\n        "signals": matching,\n    }\n\n\ndef infer_region_from_text(value: Any) -> str:\n    """Compatibility wrapper returning the legacy market/catalog region."""\n    return str(infer_region_evidence(value).get("market_region") or "UNKNOWN")\n\n\ndef infer_edition_from_text(value: Any) -> str:\n    """Return KR/JP/EN without conflating EN with the US sales market."""\n    return str(infer_region_evidence(value).get("edition_language") or "UNKNOWN")\n'''
patch("card_identity_recognition.py", old, new)

patch(
    "card_identity_recognition.py",
    '    requested_region = normalize_region(payload.get("region"))\n    region = requested_region\n',
    '    requested_edition = normalize_edition_language(payload.get("edition_language") or payload.get("region"))\n'
    '    requested_region = market_region_for_edition(requested_edition)\n'
    '    region = requested_region\n',
)

old = '''    inferred_region = str(region_evidence.get("region") or "UNKNOWN")\n    region_conflict = bool(region_evidence.get("conflict")) or (\n        region in {"KR", "JP", "US"}\n        and inferred_region in {"KR", "JP", "US"}\n        and inferred_region != region\n    )\n'''
new = '''    inferred_region = str(region_evidence.get("market_region") or region_evidence.get("region") or "UNKNOWN")\n    inferred_edition = str(region_evidence.get("edition_language") or edition_language_for_market_region(inferred_region))\n    region_conflict = bool(region_evidence.get("conflict")) or (\n        requested_edition in EDITION_LANGUAGES - {"UNKNOWN"}\n        and inferred_edition in EDITION_LANGUAGES - {"UNKNOWN"}\n        and inferred_edition != requested_edition\n    )\n'''
patch("card_identity_recognition.py", old, new)

patch(
    "card_identity_recognition.py",
    '    candidates = sorted(unique.values(), key=lambda row: -float(row.get("confidence") or 0.0))[:5]\n    ambiguity = _candidate_ambiguity(candidates, region)\n',
    '    candidates = sorted(unique.values(), key=lambda row: -float(row.get("confidence") or 0.0))[:5]\n'
    '    for row in candidates:\n'
    '        row["market_region"] = normalize_region(row.get("region"))\n'
    '        row["edition_language"] = edition_language_for_market_region(row["market_region"])\n'
    '    ambiguity = _candidate_ambiguity(candidates, region)\n',
)

patch(
    "card_identity_recognition.py",
    '        "ok": True, "game": game, "region_hint": region, "requested_region": requested_region,\n        "inferred_region": inferred_region,\n',
    '        "ok": True, "game": game, "region_hint": region, "market_region": region,\n'
    '        "edition_language": edition_language_for_market_region(region),\n'
    '        "requested_region": requested_region, "requested_edition_language": requested_edition,\n'
    '        "inferred_region": inferred_region, "inferred_edition_language": inferred_edition,\n',
)

patch(
    "card_identity_recognition.py",
    '    incoming_region = normalize_region(\n        payload.get("region") or (known.get(market_key) or {}).get("region") or "UNKNOWN"\n    )\n',
    '    incoming_edition = normalize_edition_language(\n'
    '        payload.get("edition_language") or payload.get("region")\n'
    '        or edition_language_for_market_region((known.get(market_key) or {}).get("region"))\n'
    '    )\n'
    '    incoming_region = market_region_for_edition(incoming_edition)\n',
)

patch(
    "card_identity_recognition.py",
    '                    item["region"] = effective_region\n                    promoted = True\n',
    '                    item["region"] = effective_region\n'
    '                    item["edition_language"] = edition_language_for_market_region(effective_region)\n'
    '                    promoted = True\n',
)
patch(
    "card_identity_recognition.py",
    '                "market_key": market_key, "game": game, "region": effective_region, "confirmed": True,\n',
    '                "market_key": market_key, "game": game, "region": effective_region,\n'
    '                "edition_language": edition_language_for_market_region(effective_region), "confirmed": True,\n',
)
patch(
    "card_identity_recognition.py",
    '            "region": effective_region, "identity_confirmations": count,\n',
    '            "region": effective_region, "edition_language": edition_language_for_market_region(effective_region),\n'
    '            "identity_confirmations": count,\n',
)

# Browser identity keeps legacy US market compatibility but exposes EN explicitly.
normalize_region_line = "function normalizeRegion(value){const r=generationText(value).replace(/\\s+/g,'');if(['JP','JPN','JAPAN','JAPANESE','日本','日版','日本版','일본판','일판'].includes(r))return 'JP';if(['US','USA','EN','ENGLISH','ENG','영문판','영판','미국판'].includes(r))return 'US';if(['KR','KOR','KOREA','KOREAN','한국','한국판','한글판','한판','국판'].includes(r))return 'KR';return 'UNKNOWN'}\n"
patch(
    "card_identity_recognition.js",
    normalize_region_line,
    normalize_region_line
    + "const EDITION_CODES=new Set(['KR','JP','EN']);\n"
    + "function normalizeEditionLanguage(value){const region=normalizeRegion(value);return region==='US'?'EN':region}\n"
    + "function marketRegionForEdition(value){const edition=normalizeEditionLanguage(value);return edition==='EN'?'US':edition}\n",
)

old = " const regions=[...new Set(signals.map(row=>row.region))].sort();\n if(regions.length>1)return {region:'UNKNOWN',confidence:0,basis:'edition_evidence_conflict',conflict:true,signals};\n if(!regions.length)return {region:'UNKNOWN',confidence:0,basis:'insufficient_evidence',conflict:false,signals:[]};\n const region=regions[0],matching=signals.filter(row=>row.region===region);\n return {region,confidence:Math.max(...matching.map(row=>row.confidence)),basis:[...new Set(matching.map(row=>row.basis))].join('+'),conflict:false,signals:matching};\n"
new = " const regions=[...new Set(signals.map(row=>row.region))].sort();\n if(regions.length>1)return {region:'UNKNOWN',market_region:'UNKNOWN',edition_language:'UNKNOWN',confidence:0,basis:'edition_evidence_conflict',conflict:true,signals};\n if(!regions.length)return {region:'UNKNOWN',market_region:'UNKNOWN',edition_language:'UNKNOWN',confidence:0,basis:'insufficient_evidence',conflict:false,signals:[]};\n const region=regions[0],matching=signals.filter(row=>row.region===region),edition_language=normalizeEditionLanguage(region);\n return {region,market_region:region,edition_language,confidence:Math.max(...matching.map(row=>row.confidence)),basis:[...new Set(matching.map(row=>row.basis))].join('+'),conflict:false,signals:matching};\n"
patch("card_identity_recognition.js", old, new)

patch(
    "card_identity_recognition.js",
    "window.TCGPokemonGeneration=Object.freeze({version:'v325',infer:inferPokemonGeneration,render:renderPokemonGeneration,inferRegion:inferEditionFromText});",
    "window.TCGPokemonGeneration=Object.freeze({version:'v328',infer:inferPokemonGeneration,render:renderPokemonGeneration,inferRegion:inferEditionFromText,normalizeEditionLanguage,marketRegionForEdition});",
)
patch(
    "card_identity_recognition.js",
    "if(allowRegionAutofill&&current==='UNKNOWN'&&candidateRegion!=='UNKNOWN'&&byId('identityRegion'))byId('identityRegion').value=candidateRegion;",
    "if(allowRegionAutofill&&current==='UNKNOWN'&&candidateRegion!=='UNKNOWN'&&byId('identityRegion'))byId('identityRegion').value=normalizeEditionLanguage(candidateRegion);",
)
patch(
    "card_identity_recognition.js",
    "body:JSON.stringify({game:resolvedGame,region,image_hash:hash,image_data:data,ocr_text:text})",
    "body:JSON.stringify({game:resolvedGame,region,edition_language:normalizeEditionLanguage(byId('identityRegion')?.value||region),image_hash:hash,image_data:data,ocr_text:text})",
)
patch(
    "card_identity_recognition.js",
    "if(selected==='UNKNOWN'&&effectiveRegion!=='UNKNOWN'&&byId('identityRegion'))byId('identityRegion').value=effectiveRegion;",
    "if(selected==='UNKNOWN'&&effectiveRegion!=='UNKNOWN'&&byId('identityRegion'))byId('identityRegion').value=normalizeEditionLanguage(effectiveRegion);",
)
patch(
    "card_identity_recognition.js",
    "edition=normalizeRegion(byId('identityRegion')?.value||'UNKNOWN');status.textContent=",
    "edition=normalizeEditionLanguage(byId('identityRegion')?.value||'UNKNOWN');status.textContent=",
)
patch(
    "card_identity_recognition.js",
    "const row={confirmed:true,image_hash:hash,game,card_name:name,card_number:number,market_key:safeText(byId('identityMarketKey').value),region};",
    "const row={confirmed:true,image_hash:hash,game,card_name:name,card_number:number,market_key:safeText(byId('identityMarketKey').value),region,edition_language:normalizeEditionLanguage(byId('identityRegion').value)};",
)

patch(
    "index.html",
    '<label>국가<select id="identityRegion"><option>KR</option><option>JP</option><option>US</option><option>UNKNOWN</option></select></label>',
    '<label>언어·판본<select id="identityRegion"><option value="KR">KR</option><option value="JP">JP</option><option value="EN">EN</option><option value="UNKNOWN">UNKNOWN</option></select></label>',
)
patch(
    "auto_market_center.js",
    "function normRegion(v){return ['KR','JP','US'].includes(v)?v:'ALL'}",
    "function normRegion(v){const raw=String(v||'').toUpperCase();return raw==='EN'?'US':(['KR','JP','US'].includes(raw)?raw:'ALL')}",
)
patch(
    "grade_market_flow.js",
    " if(/(^|\\b)(us|usa|english)(\\b|$)|미국|미국판|영문판/.test(low))return 'US';",
    " if(/(^|\\b)(us|usa|en|english)(\\b|$)|미국|미국판|영문판/.test(low))return 'US';",
)
patch(
    "grade_market_flow.js",
    "function editionLabel(code){return ({KR:'🇰🇷 한국판',JP:'🇯🇵 일본판',US:'🇺🇸 미국/영문판',UNKNOWN:'🌐 판본 미확인'})[code]||'🌐 판본 미확인'}",
    "function editionLabel(code){return ({KR:'🇰🇷 한국판',JP:'🇯🇵 일본판',US:'🌐 영문판(EN)',UNKNOWN:'🌐 판본 미확인'})[code]||'🌐 판본 미확인'}",
)

# ---------------------------------------------------------------------------
# FX: producer timestamp must be enforced by every consumer. A stale/invalid
# foreign rate becomes unavailable; never silently substitute hard-coded FX.
# ---------------------------------------------------------------------------
old = '''def _fx():\n    d=_safe_json(FX,{})\n    rates=d.get('rates') if isinstance(d,dict) else {}\n    return {'USD':float((rates or {}).get('USD_KRW') or 0),'JPY':float((rates or {}).get('JPY_KRW') or 0),\n            'EUR':float((rates or {}).get('EUR_KRW') or 0),'KRW':1.0}\n'''
new = '''FX_MAX_AGE_SECONDS=72*60*60\nFX_MAX_FUTURE_SKEW_SECONDS=6*60*60\n\ndef _fx():\n    d=_safe_json(FX,{})\n    rates=d.get('rates') if isinstance(d,dict) else {}\n    stamp=str(d.get('updated_at') or '') if isinstance(d,dict) else ''\n    try:\n        parsed=datetime.fromisoformat(stamp.replace('Z','+00:00'))\n        if parsed.tzinfo is None:\n            raise ValueError('timezone_required')\n        age=(datetime.now(timezone.utc)-parsed.astimezone(timezone.utc)).total_seconds()\n        fresh=(-FX_MAX_FUTURE_SKEW_SECONDS <= age <= FX_MAX_AGE_SECONDS)\n    except (TypeError,ValueError,OverflowError):\n        fresh=False\n    if not fresh:\n        return {'USD':0.0,'JPY':0.0,'EUR':0.0,'KRW':1.0}\n    return {'USD':float((rates or {}).get('USD_KRW') or 0),'JPY':float((rates or {}).get('JPY_KRW') or 0),\n            'EUR':float((rates or {}).get('EUR_KRW') or 0),'KRW':1.0}\n'''
patch("multi_market_price_collector.py", old, new)

patch(
    "index.html",
    'let fxRates={JPY_KRW:8.72295,USD_KRW:1386.89},fxUpdated="2026-08-21";',
    'let fxRates={JPY_KRW:0,USD_KRW:0},fxUpdated="";',
)
patch(
    "index.html",
    "async function loadExchangeRates(force=false){",
    "const FX_MAX_AGE_MS=72*60*60*1000,FX_MAX_FUTURE_SKEW_MS=6*60*60*1000;\n"
    "function fxTimestampFresh(value,now=Date.now()){const parsed=Date.parse(String(value||''));if(!Number.isFinite(parsed))return false;const age=now-parsed;return age>=-FX_MAX_FUTURE_SKEW_MS&&age<=FX_MAX_AGE_MS}\n"
    "async function loadExchangeRates(force=false){",
)
patch(
    "index.html",
    '  const d=await r.json(),jpy=Number(d.rates?.JPY_KRW),usd=Number(d.rates?.USD_KRW);\n  if(!(Number.isFinite(jpy)&&jpy>0&&jpy<30&&Number.isFinite(usd)&&usd>500&&usd<3000))throw new Error("fx schema");\n  fxRates={JPY_KRW:jpy,USD_KRW:usd};fxUpdated=String(d.updated_at||"").slice(0,10)||fxUpdated;result.ok=true;',
    '  const d=await r.json(),jpy=Number(d.rates?.JPY_KRW),usd=Number(d.rates?.USD_KRW),stamp=String(d.updated_at||"");\n  if(!(Number.isFinite(jpy)&&jpy>0&&jpy<30&&Number.isFinite(usd)&&usd>500&&usd<3000))throw new Error("fx schema");\n  if(!fxTimestampFresh(stamp))throw new Error("fx timestamp stale");\n  fxRates={JPY_KRW:jpy,USD_KRW:usd};fxUpdated=stamp.slice(0,10)||fxUpdated;result.ok=true;',
)

# Browser-runtime fixture must model a freshly fetched FX document.
patch(
    "verify_browser_runtime.js",
    '{ rates: { JPY_KRW: 8.7, USD_KRW: 1380 }, updated_at: "2026-08-25" },',
    '{ rates: { JPY_KRW: 8.7, USD_KRW: 1380 }, updated_at: new Date().toISOString() },',
)

# New integrated regression. Existing legacy region assertions remain unchanged;
# this test proves the new edition-language contract and stale-FX fail-closed path.
(ROOT / "test_edition_fx_failclosed_v328.py").write_text(
    '''from __future__ import annotations\n\nimport json\nimport tempfile\nimport unittest\nfrom datetime import datetime, timedelta, timezone\nfrom pathlib import Path\nfrom unittest import mock\n\nimport card_identity_recognition as identity\nimport multi_market_price_collector as market\n\nROOT=Path(__file__).resolve().parent\n\nclass EditionFxFailClosedV328Tests(unittest.TestCase):\n    def test_english_edition_is_distinct_from_us_market(self):\n        self.assertEqual("EN", identity.normalize_edition_language("EN"))\n        self.assertEqual("US", identity.market_region_for_edition("EN"))\n        self.assertEqual("EN", identity.edition_language_for_market_region("US"))\n        evidence=identity.infer_region_evidence("EN Pikachu PAL 185/193")\n        self.assertEqual("EN", evidence["edition_language"])\n        self.assertEqual("US", evidence["market_region"])\n        self.assertFalse(evidence["conflict"])\n        result=identity.recognize({"game":"pokemon","edition_language":"EN","image_hash":"0"*16,"ocr_text":"Pikachu PAL 185/193"})\n        self.assertEqual("EN", result["edition_language"])\n        self.assertEqual("US", result["market_region"])\n        self.assertEqual("EN", result["requested_edition_language"])\n\n    def test_mixed_hangul_kana_remains_fail_closed(self):\n        evidence=identity.infer_region_evidence("포켓몬 카드 ポケモン カード")\n        self.assertTrue(evidence["conflict"])\n        self.assertEqual("UNKNOWN", evidence["edition_language"])\n        self.assertEqual("UNKNOWN", evidence["market_region"])\n\n    def test_stale_fx_is_not_used(self):\n        with tempfile.TemporaryDirectory() as directory:\n            path=Path(directory)/"exchange_rates.json"\n            path.write_text(json.dumps({"updated_at":"2000-01-01T00:00:00+00:00","rates":{"JPY_KRW":9.1,"USD_KRW":1400.0}}),encoding="utf-8")\n            with mock.patch.object(market,"FX",path):\n                rates=market._fx()\n            self.assertEqual(0.0,rates["JPY"])\n            self.assertEqual(0.0,rates["USD"])\n            self.assertEqual(1.0,rates["KRW"])\n\n    def test_fresh_fx_is_accepted(self):\n        with tempfile.TemporaryDirectory() as directory:\n            path=Path(directory)/"exchange_rates.json"\n            stamp=(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()\n            path.write_text(json.dumps({"updated_at":stamp,"rates":{"JPY_KRW":9.1,"USD_KRW":1400.0}}),encoding="utf-8")\n            with mock.patch.object(market,"FX",path):\n                rates=market._fx()\n            self.assertEqual(9.1,rates["JPY"])\n            self.assertEqual(1400.0,rates["USD"])\n\n    def test_ui_has_explicit_edition_and_no_static_fx_fallback(self):\n        html=(ROOT/"index.html").read_text(encoding="utf-8")\n        browser=(ROOT/"card_identity_recognition.js").read_text(encoding="utf-8")\n        market_ui=(ROOT/"auto_market_center.js").read_text(encoding="utf-8")\n        self.assertIn('언어·판본<select id="identityRegion">',html)\n        self.assertIn('<option value="EN">EN</option>',html)\n        self.assertIn('let fxRates={JPY_KRW:0,USD_KRW:0},fxUpdated="";',html)\n        self.assertIn('FX_MAX_AGE_MS',html)\n        self.assertIn('fxTimestampFresh',html)\n        self.assertIn('normalizeEditionLanguage',browser)\n        self.assertIn('marketRegionForEdition',browser)\n        self.assertIn("raw==='EN'?'US'",market_ui)\n\nif __name__=='__main__':\n    unittest.main(verbosity=2)\n''',
    encoding="utf-8",
)

patch(
    "verify_pokemon_generation_runtime.js",
    "eq(api.version,'v325','generation runtime version');",
    "eq(api.version,'v328','generation runtime version');",
)
patch(
    "verify_pokemon_generation_runtime.js",
    "console.log('Pokémon generation runtime v325: PASS');",
    "console.log('Pokémon generation runtime v328: PASS');",
)

patch(
    "test_card_region_generation_precision_v306.py",
    "Pokémon generation runtime v325: PASS",
    "Pokémon generation runtime v328: PASS",
)
patch(
    "test_card_identity_ambiguity_v320.py",
    "Pokémon generation runtime v325: PASS",
    "Pokémon generation runtime v328: PASS",
)

patch(
    "verify_browser_runtime.js",
    '  loadAsyncBlock("loadExchangeRates");',
    '  context.FX_MAX_AGE_MS=72*60*60*1000;\n'
    '  context.FX_MAX_FUTURE_SKEW_MS=6*60*60*1000;\n'
    '  loadOneLine("fxTimestampFresh");\n'
    '  loadAsyncBlock("loadExchangeRates");',
)

print("v328 patch applied")

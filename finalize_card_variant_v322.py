#!/usr/bin/env python3
from pathlib import Path


def patch(path: str, old: str, new: str, label: str) -> None:
    p = Path(path)
    s = p.read_text(encoding="utf-8")
    n = s.count(old)
    if n != 1:
        raise SystemExit(f"{label}: anchor count={n}")
    p.write_text(s.replace(old, new, 1), encoding="utf-8")


# Explicit print evidence must not match an UNKNOWN print candidate.
old = '''        for field in ("set_code", "variant", "finish", "rarity"):
            wanted = query_meta.get(field) or ("UNKNOWN" if field != "set_code" else "")
            actual = row_meta.get(field) or ("UNKNOWN" if field != "set_code" else "")
            wanted_known = bool(wanted and wanted != "UNKNOWN")
            actual_known = bool(actual and actual != "UNKNOWN")
            if wanted_known and actual_known and wanted != actual:
                break
        else:
            pass
        if any(
            (query_meta.get(field) not in (None, "", "UNKNOWN"))
            and (row_meta.get(field) not in (None, "", "UNKNOWN"))
            and query_meta.get(field) != row_meta.get(field)
            for field in ("set_code", "variant", "finish", "rarity")
        ):
            continue
'''
new = '''        if any(
            (query_meta.get(field) not in (None, "", "UNKNOWN"))
            and (row_meta.get(field) in (None, "", "UNKNOWN") or query_meta.get(field) != row_meta.get(field))
            for field in ("set_code", "variant", "finish", "rarity")
        ):
            continue
'''
patch("card_identity_recognition.py", old, new, "strict catalog metadata")

# Quick price search uses structured identity instead of a broad contiguous blob query.
old = """ async function quickPrice(){const q=S('quickCardQuery').value.trim().toLowerCase();if(!q){S('quickPriceResults').textContent='카드명 또는 카드번호를 입력하세요.';return}S('quickPriceResults').textContent='시세자료 검색 중…';try{const r=await fetch(`market_prices.json?t=${Date.now()}`,{cache:'no-store'}),d=await r.json(),entries=d.entries&&typeof d.entries==='object'?d.entries:{};const gameNeed=simpleGame==='pokemon'?'pok':simpleGame==='onepiece'?'one':'nar';let hits=[];for(const [k,v] of Object.entries(entries)){const blob=(k+' '+JSON.stringify(v)).toLowerCase();if(blob.includes(q)&&(!gameNeed||blob.includes(gameNeed)||blob.includes(profiles[simpleGame].name.toLowerCase())))hits.push([k,v]);}if(!hits.length){for(const [k,v] of Object.entries(entries)){const blob=(k+' '+JSON.stringify(v)).toLowerCase();if(blob.includes(q))hits.push([k,v]);}}hits=hits.slice(0,12);if(!hits.length){S('quickPriceResults').innerHTML='저장된 시세자료에서 일치 항목을 찾지 못했습니다. <b>카드번호까지 같이 입력</b>하면 정확도가 올라갑니다.';return}S('quickPriceResults').innerHTML=hits.map(([k,v])=>`<div class=\"price-item\"><b>${escapeDisplayText(k)}</b><br><span class=\"muted\">${Object.entries(v&&typeof v==='object'?v:{}).filter(([a,b])=>['string','number'].includes(typeof b)).slice(0,8).map(([a,b])=>`${escapeDisplayText(a)}: ${escapeDisplayText(b)}`).join(' · ')}</span></div>`).join('');}catch(e){S('quickPriceResults').textContent='시세자료를 불러오지 못했습니다. 업데이트 후 다시 시도하세요.'}}
"""
new = """ function quickPriceIdentityMeta(row,key){const infer=window.TCGCardIdentityMeta?.infer;if(typeof infer!=='function')return {set_code:'',variant:'UNKNOWN',finish:'UNKNOWN',rarity:'UNKNOWN'};return infer({game:row?.game||simpleGame,card_name:row?.card_name||String(key||'').split('|')[1]||'',card_number:row?.card_number||'',market_key:key||'',product_name:row?.product_name||'',set_code:row?.set_code||'',variant:row?.variant||'UNKNOWN',finish:row?.finish||'UNKNOWN',rarity:row?.rarity||'UNKNOWN'})}
 function quickPriceIdentityCompatible(target,actual){for(const field of ['set_code','variant','finish','rarity']){const t=target?.[field]||'',a=actual?.[field]||'',tk=Boolean(t&&t!=='UNKNOWN'),ak=Boolean(a&&a!=='UNKNOWN');if(tk&&(!ak||t!==a))return false}return true}
 async function quickPrice(){const q=S('quickCardQuery').value.trim().toLowerCase(),name=String(S('identityCardName')?.value||'').trim().toLowerCase(),number=String(S('identityCardNumber')?.value||'').trim().toLowerCase().replace(/\\s+/g,''),region=String(S('identityRegion')?.value||'UNKNOWN').toUpperCase(),infer=window.TCGCardIdentityMeta?.infer,targetMeta=typeof infer==='function'?infer({game:simpleGame,card_name:name,card_number:number,ocr_text:window.tcgIdentityOcrText||'',set_code:S('identitySetCode')?.value||'',variant:S('identityVariant')?.value||'UNKNOWN',finish:S('identityFinish')?.value||'UNKNOWN',rarity:S('identityRarity')?.value||''}):{set_code:'',variant:'UNKNOWN',finish:'UNKNOWN',rarity:'UNKNOWN'},structured=Boolean(name||number||region!=='UNKNOWN'||targetMeta.set_code||targetMeta.variant!=='UNKNOWN'||targetMeta.finish!=='UNKNOWN'||targetMeta.rarity!=='UNKNOWN');if(!q&&!structured){S('quickPriceResults').textContent='카드명 또는 카드번호를 입력하세요.';return}S('quickPriceResults').textContent='시세자료 검색 중…';try{const r=await fetch(`market_prices.json?t=${Date.now()}`,{cache:'no-store'}),d=await r.json(),entries=d.entries&&typeof d.entries==='object'?d.entries:{},gameNeed=simpleGame==='pokemon'?'pok':simpleGame==='onepiece'?'one':'nar',manualTokens=q.split(/\\s+/).filter(Boolean);let ranked=[];for(const [k,v] of Object.entries(entries)){const blob=(k+' '+JSON.stringify(v)).toLowerCase(),keyRegion=String(k).split('|',1)[0].toUpperCase();if(structured){if(region!=='UNKNOWN'&&keyRegion!==region)continue;if(!blob.includes(gameNeed)&&!blob.includes(profiles[simpleGame].name.toLowerCase())&&String(v?.game||'').toLowerCase()!==simpleGame)continue;const rowNumber=String(v?.card_number||'').toLowerCase().replace(/\\s+/g,'');if(number&&rowNumber&&rowNumber!==number)continue;if(number&&!rowNumber&&!blob.replace(/\\s+/g,'').includes(number))continue;if(name&&!blob.includes(name))continue;const actualMeta=quickPriceIdentityMeta(v,k);if(!quickPriceIdentityCompatible(targetMeta,actualMeta))continue;let score=(number?100:0)+(name?50:0)+(region!=='UNKNOWN'?20:0);for(const field of ['set_code','variant','finish','rarity'])if(targetMeta[field]&&targetMeta[field]!=='UNKNOWN'&&targetMeta[field]===actualMeta[field])score+=10;ranked.push([score,k,v]);}else if(manualTokens.length&&manualTokens.every(token=>blob.includes(token)))ranked.push([manualTokens.length,k,v]);}ranked.sort((a,b)=>b[0]-a[0]||String(a[1]).localeCompare(String(b[1])));const hits=ranked.slice(0,12).map(([,k,v])=>[k,v]);if(!hits.length){S('quickPriceResults').innerHTML=structured?'저장된 시세자료에서 <b>같은 게임·판본·카드번호·세트/버전</b>까지 확인된 항목을 찾지 못했습니다. 다른 버전 가격으로 자동 대체하지 않았습니다.':'저장된 시세자료에서 검색어 전체가 일치하는 항목을 찾지 못했습니다.';return}S('quickPriceResults').innerHTML=hits.map(([k,v])=>`<div class=\"price-item\"><b>${escapeDisplayText(k)}</b><br><span class=\"muted\">${Object.entries(v&&typeof v==='object'?v:{}).filter(([a,b])=>['string','number'].includes(typeof b)).slice(0,8).map(([a,b])=>`${escapeDisplayText(a)}: ${escapeDisplayText(b)}`).join(' · ')}</span></div>`).join('');}catch(e){S('quickPriceResults').textContent='시세자료를 불러오지 못했습니다. 업데이트 후 다시 시도하세요.'}}
"""
patch("index.html", old, new, "structured quick price")

# Persist conservative print metadata in WYYYES quote rows.
anchor = '''def infer_grade(text: str) -> tuple[str, int | None]:
    value = text or ""
    match = re.search(r"\\b(PSA|BGS|CGC|TAG|BRG)\\s*[-:]?\\s*(10|[1-9])\\b", value, re.I)
    if not match:
        return "", None
    return match.group(1).upper(), int(match.group(2))


'''
helpers = r'''def infer_set_code(text: str) -> str:
    value = (text or "").upper()
    match = re.search(r"(?<![A-Z0-9])(OP|ST|EB|PRB)-?(\d{1,2})(?![A-Z0-9])", value)
    if match:
        return f"{match.group(1)}{int(match.group(2)):02d}"
    match = re.search(r"(?<![A-Z0-9])(MEG|PFL|ASC|POR|CRI|PBL|SVI|PAL|OBF|MEW|PAR|PAF|TEF|TWM|SFA|SCR|SSP|PRE|JTG|DRI|BLK|WHT)(?=\s*[- ]?\s*\d{1,3}|[^A-Z0-9]|$)", value)
    if match:
        return match.group(1)
    match = re.search(r"(?<![A-Z0-9])((?:SV|SM|S|M|XY|BW|DPT?|DP)\d{1,2}[A-Z]{0,2})(?=\d|[-/\s]|$)", re.sub(r"\s+", "", value))
    return match.group(1) if match else ""


def infer_variant(text: str) -> str:
    value = text or ""
    rules = (
        ("MANGA", r"(?:\bMANGA(?:\s+RARE)?\b|만화\s*패러렐|망가\s*패러렐|コミパラ)"),
        ("ALT_ART", r"(?:\bALT(?:ERNATE|ERNATIVE)?\s*ART\b|\bALT\s*ART\b|얼터너티브\s*아트|대체\s*일러스트)"),
        ("FULL_ART", r"(?:\bFULL\s*ART\b|풀\s*아트|\bFA\b)"),
        ("SPECIAL_ART", r"(?:\bSPECIAL\s*ART\b|스페셜\s*아트)"),
        ("PROMO", r"(?:\bPROMO(?:TIONAL)?\b|프로모|プロモ)"),
        ("STAMPED", r"(?:\bSTAMPED\b|스탬프|スタンプ)"),
        ("FIRST_EDITION", r"(?:\b1ST\s*EDITION\b|\bFIRST\s*EDITION\b|초판)"),
        ("PARALLEL", r"(?:\bPARALLEL\b|패러렐|パラレル|(?<![A-Z0-9])(?:R|L|SR|SEC)-P(?![A-Z0-9]))"),
    )
    for label, pattern in rules:
        if re.search(pattern, value, re.I):
            return label
    return "UNKNOWN"


def infer_finish(text: str) -> str:
    value = text or ""
    if re.search(r"(?:\bREVERSE\s*HOLO(?:FOIL)?\b|리버스\s*홀로|リバース)", value, re.I):
        return "REVERSE_HOLO"
    if re.search(r"(?:\bNON[- ]?HOLO\b|논\s*홀로)", value, re.I):
        return "NON_HOLO"
    if re.search(r"(?:\bHOLO(?:GRAPHIC|FOIL)?\b|홀로|ホロ)", value, re.I):
        return "HOLO"
    if re.search(r"(?:\bFOIL\b|포일|箔)", value, re.I):
        return "FOIL"
    return "UNKNOWN"


def infer_rarity(text: str) -> str:
    value = (text or "").upper()
    for rarity in ("BWR", "MUR", "SAR", "CSR", "CHR", "SSR", "RRR", "SEC", "SR", "UR", "HR", "AR", "SP", "TR", "RR"):
        if re.search(rf"(?<![A-Z0-9]){rarity}(?![A-Z0-9])", value):
            return rarity
    return "UNKNOWN"


'''
patch("wyyyes_market_source.py", anchor, anchor + helpers, "wyyyes metadata helpers")
old = '''    card_number = _card_number(identity_text) or _card_number(page_text[:8_000])
    # Transaction state must be product-local.  A generic footer, recommendation
'''
new = '''    card_number = _card_number(identity_text) or _card_number(page_text[:8_000])
    set_code = infer_set_code(" ".join((identity_text, card_number)))
    variant = infer_variant(identity_text)
    finish = infer_finish(identity_text)
    rarity = infer_rarity(identity_text)
    # Transaction state must be product-local.  A generic footer, recommendation
'''
patch("wyyyes_market_source.py", old, new, "wyyyes metadata parse")
old = '''        "title": title,
        "card_number": card_number,
        "grading_company": company,
'''
new = '''        "title": title,
        "card_number": card_number,
        "set_code": set_code,
        "variant": variant,
        "finish": finish,
        "rarity": rarity,
        "grading_company": company,
'''
patch("wyyyes_market_source.py", old, new, "wyyyes metadata output")

# Extend WYYYES regression.
test = Path("test_wyyyes_market_source_v267.py")
s = test.read_text(encoding="utf-8")
marker = '''    def test_unrelated_page_sold_badge_cannot_promote_listing(self):
'''
extra = '''    def test_public_listing_preserves_print_identity_metadata(self):
        html = """
        <html><body>
          <h1>Portgas D. Ace OP13-119 Manga Parallel SEC Holo Japanese One Piece Card</h1>
          <meta itemprop="price" content="880000">
          <p>가격 제안하기</p>
        </body></html>
        """
        row = wyyyes.parse_public_listing(html, "https://wyyyes.com/category/trading-cards/9999997")
        self.assertIsNotNone(row)
        self.assertEqual("JP", row["card_region"])
        self.assertEqual("OP13-119", row["card_number"])
        self.assertEqual("OP13", row["set_code"])
        self.assertEqual("MANGA", row["variant"])
        self.assertEqual("HOLO", row["finish"])
        self.assertEqual("SEC", row["rarity"])

'''
if s.count(marker) != 1:
    raise SystemExit(f"wyyyes test marker count={s.count(marker)}")
test.write_text(s.replace(marker, extra + marker, 1), encoding="utf-8")

# Extend v322 integration regression.
vtest = Path("test_card_variant_market_precision_v322.py")
s = vtest.read_text(encoding="utf-8")
old = '''        self.assertIn("identitySetCode", validation)
        self.assertIn("identityVariant", validation)
'''
new = '''        self.assertIn("identitySetCode", validation)
        self.assertIn("identityVariant", validation)
        self.assertIn("quickPriceIdentityCompatible", page)
        self.assertIn("다른 버전 가격으로 자동 대체하지 않았습니다", page)
'''
if s.count(old) != 1:
    raise SystemExit(f"v322 test marker count={s.count(old)}")
vtest.write_text(s.replace(old, new, 1), encoding="utf-8")

# Current runtime must execute WYYYES print-metadata regression too.
verify = Path("verify_current_runtime.py")
s = verify.read_text(encoding="utf-8")
old = '"test_card_variant_market_precision_v322.py","test_multi_market_price_collector.py"'
new = '"test_card_variant_market_precision_v322.py","test_wyyyes_market_source_v267.py","test_multi_market_price_collector.py"'
if s.count(old) != 1:
    raise SystemExit(f"verify wyyyes anchor count={s.count(old)}")
verify.write_text(s.replace(old, new, 1), encoding="utf-8")

print("v322 final print-identity hardening applied")

#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, got {count}")
    return text.replace(old, new, 1)


def replace_span(text: str, start: str, end: str, replacement: str, label: str) -> str:
    a = text.find(start)
    if a < 0:
        raise RuntimeError(f"{label}: start marker missing")
    b = text.find(end, a + len(start))
    if b < 0:
        raise RuntimeError(f"{label}: end marker missing")
    return text[:a] + replacement.rstrip() + "\n" + text[b:]


def replace_py_function(text: str, name: str, replacement: str) -> str:
    pattern = re.compile(rf"^def {re.escape(name)}\([^\n]*\).*?(?=^def |\Z)", re.M | re.S)
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise RuntimeError(f"python function {name}: expected one match, got {len(matches)}")
    m = matches[0]
    return text[:m.start()] + replacement.rstrip() + "\n\n" + text[m.end():]


def patch_server_identity() -> None:
    path = "card_identity_recognition.py"
    text = read(path)
    replacement = r'''def _candidate_identity_signature(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        normalize_game(row.get("game")),
        normalize_region(row.get("region")),
        normalize(row.get("card_name")),
        normalize_number(row.get("card_number")),
        str(row.get("market_key") or "").strip(),
    )


def _candidate_ambiguity(candidates: list[dict[str, Any]], requested_region: str) -> dict[str, Any]:
    if not candidates:
        return {
            "identity_ambiguous": False,
            "region_ambiguous": False,
            "market_ambiguous": False,
            "contender_count": 0,
            "regions": [],
            "top_confidence": 0.0,
        }
    top = max(0.0, min(1.0, float(candidates[0].get("confidence") or 0.0)))
    # Only high-confidence candidates close enough to the top can block automatic
    # selection. Lower-scored alternatives remain visible for manual review.
    contenders = [
        row for row in candidates
        if float(row.get("confidence") or 0.0) >= 0.90
        and top - float(row.get("confidence") or 0.0) <= 0.02
    ]
    signatures = {_candidate_identity_signature(row) for row in contenders}
    regions = sorted({
        normalize_region(row.get("region")) for row in contenders
        if normalize_region(row.get("region")) in {"KR", "JP", "US"}
    })
    market_keys = {str(row.get("market_key") or "").strip() for row in contenders if str(row.get("market_key") or "").strip()}
    requested_region = normalize_region(requested_region)
    region_ambiguous = requested_region == "UNKNOWN" and len(regions) > 1
    # Distinct edition rows are distinct identities for automatic selection even
    # when the printed name/number is identical.
    identity_ambiguous = len(signatures) > 1
    market_ambiguous = len(market_keys) > 1
    return {
        "identity_ambiguous": identity_ambiguous,
        "region_ambiguous": region_ambiguous,
        "market_ambiguous": market_ambiguous,
        "contender_count": len(contenders),
        "regions": regions,
        "top_confidence": round(top, 4),
    }


def recognize(payload: dict[str, Any]) -> dict[str, Any]:
    game = normalize_game(payload.get("game"))
    if game not in GAMES:
        raise ValueError("게임 구분 오류")
    requested_region = normalize_region(payload.get("region"))
    region = requested_region
    supplied_text = str(payload.get("ocr_text") or "")[:MAX_OCR_TEXT]
    image_data = payload.get("image_data")
    image_hash = str(payload.get("image_hash") or "").lower()
    ocr_error = None
    ocr_diagnostics: dict[str, Any] = {}
    if image_data:
        data = _decode_image(image_data)
        image_hash = image_dhash(data)
        text, ocr_error, ocr_diagnostics = ocr_image_detailed(
            data, game=game, region=region, seed_text=supplied_text
        )
        supplied_text = (supplied_text + " " + text).strip()[:MAX_OCR_TEXT]
    region_evidence = infer_region_evidence(supplied_text)
    inferred_region = str(region_evidence.get("region") or "UNKNOWN")
    region_conflict = bool(region_evidence.get("conflict")) or (
        region in {"KR", "JP", "US"}
        and inferred_region in {"KR", "JP", "US"}
        and inferred_region != region
    )
    if region == "UNKNOWN" and inferred_region != "UNKNOWN":
        region = inferred_region
    elif region != "UNKNOWN" and not HASH_RE.fullmatch(image_hash):
        raise ValueError("이미지 또는 특징값 필요")
    learned = match_learning(image_hash, game, region)
    catalog_hits = match_catalog(supplied_text, game, region=region)
    merged = learned + catalog_hits
    unique: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in merged:
        key = (
            str(row.get("card_name") or ""),
            str(row.get("card_number") or ""),
            str(row.get("market_key") or ""),
            normalize_region(row.get("region")),
        )
        if key not in unique or float(row.get("confidence") or 0.0) > float(unique[key].get("confidence") or 0.0):
            unique[key] = row
    candidates = sorted(unique.values(), key=lambda row: -float(row.get("confidence") or 0.0))[:5]
    ambiguity = _candidate_ambiguity(candidates, region)
    identity_ambiguous = bool(ambiguity["identity_ambiguous"])
    region_ambiguous = bool(ambiguity["region_ambiguous"])
    market_ambiguous = bool(ambiguity["market_ambiguous"])
    auto_selection_blocked = bool(region_conflict or identity_ambiguous or region_ambiguous or market_ambiguous)
    market_link_blocked = bool(auto_selection_blocked or region == "UNKNOWN")
    return {
        "ok": True, "game": game, "region_hint": region, "requested_region": requested_region,
        "inferred_region": inferred_region,
        "region_conflict": region_conflict, "region_evidence": region_evidence,
        "region_ambiguous": region_ambiguous, "identity_ambiguous": identity_ambiguous,
        "market_ambiguous": market_ambiguous, "market_link_blocked": market_link_blocked,
        "ambiguity": ambiguity,
        "image_hash": image_hash, "ocr_text": supplied_text,
        "ocr_error": ocr_error, "ocr_diagnostics": ocr_diagnostics,
        "numbers_detected": extract_numbers(supplied_text),
        "candidates": candidates,
        "best": None if auto_selection_blocked else (candidates[0] if candidates else None),
        "auto_selection_blocked": auto_selection_blocked,
        "requires_confirmation": True,
        "policy": {"prediction_auto_learned": False, "user_confirmation_required": True,
                   "similar_image_learning_min_confirmations": 3,
                   "unknown_edition_market_link": False,
                   "ambiguous_identity_auto_selection": False},
    }'''
    text = replace_py_function(text, "recognize", replacement)
    write(path, text)


def patch_browser_identity() -> None:
    path = "card_identity_recognition.js"
    text = read(path)

    text = replace_span(
        text,
        "function generationByRegulation(mark){",
        "function generationRegion(value)",
        r'''function generationByRegulation(mark){
 if(!/^[A-J]$/.test(mark))return null;
 return {generation:null,generation_label:'세대 단정 안 함',series:`레귤레이션 ${mark} 시기`,era:'REGULATION',context_only:true};
}
function generationRegion(value)''',
        "regulation semantics",
    )

    text = replace_span(
        text,
        "function generationConflict(inputRegion,byExpansion,expansion,regulation,byReg){",
        "function inferPokemonGeneration(input={}){",
        r'''function generationConflict(inputRegion,byExpansion,expansion){
 const setRegion=normalizeRegion(byExpansion?.set_region||'UNKNOWN');
 if(inputRegion!=='UNKNOWN'&&setRegion!=='UNKNOWN'&&inputRegion!==setRegion){
  return {status:'conflict',game:'pokemon',generation:null,generation_label:'근거 충돌',series:'판본/세트코드 재확인',era:'CONFLICT',expansion_code:expansion||'',regulation_mark:'',year:null,confidence:0,confidence_level:'conflict',basis:[`선택 판본 ${inputRegion}`,`세트코드 판본 ${setRegion}`],note:'판본과 세트코드 근거가 충돌해 세대를 단정하지 않았습니다.'};
 }
 return null;
}
function inferPokemonGeneration(input={}){''',
        "generation conflict semantics",
    )

    text = replace_span(
        text,
        "function inferPokemonGeneration(input={}){",
        "function renderPokemonGeneration(info,game='pokemon'){",
        r'''function inferPokemonGeneration(input={}){
 const game=String(input.game||'pokemon').trim().toLowerCase();
 if(game!=='pokemon')return {status:'not_applicable',game,generation:null,confidence:0,basis:[]};
 const text=[input.ocr_text,input.card_name,input.market_key].map(generationText).filter(Boolean).join(' ');
 const inputRegion=normalizeRegion(input?.region),year=yearFromEvidence(input,text);
 const expansion=expansionFromCardNumber(input.card_number)||expansionFromOcr(text);
 const byExpansion=generationBySetCode(expansion);
 const regulation=regulationFromEvidence(input,text),byReg=generationByRegulation(regulation);
 const conflict=generationConflict(inputRegion,byExpansion,expansion);
 if(conflict){conflict.year=year;conflict.regulation_mark=regulation||'';return conflict}
 const timeConflict=generationYearConflict(byExpansion,year,expansion,regulation);
 if(timeConflict)return timeConflict;
 if(byExpansion){
  const generationBasis=[`확장팩/세트 코드 ${expansion}`];
  if(year)generationBasis.push(`©/제작연도 ${year}`);
  const contextBasis=byReg?[`레귤레이션 마크 ${regulation}`]:[];
  const evidence_count=generationBasis.length;
  return {status:'estimated',game:'pokemon',...byExpansion,expansion_code:expansion,regulation_mark:regulation||'',year,confidence:evidence_count>=2?.995:.98,confidence_level:'high',evidence_count,context_evidence_count:contextBasis.length,basis:[...generationBasis,...contextBasis],note:byExpansion.era==='MEGA'?'MEGA는 별도 TCG 시리즈/블록이므로 TCG 시리즈와 포켓몬 세대 번호를 분리해 표시합니다.':(byReg?'확장팩/세트 코드가 세대 근거이며 레귤레이션 마크는 사용 가능 시기 문맥으로만 표시합니다.':'확장팩/세트 코드와 독립 OCR 근거를 교차검증한 추정')};
 }
 if(byReg){
  const basis=[`레귤레이션 마크 ${regulation}`];if(year)basis.push(`©/제작연도 ${year}`);
  return {status:'context_only',game:'pokemon',...byReg,expansion_code:'',regulation_mark:regulation,year,confidence:.50,confidence_level:'context',evidence_count:0,context_evidence_count:1,basis,note:'레귤레이션 마크는 사용 가능 범위를 관리하는 표기이므로 포켓몬 세대 번호로 변환하지 않습니다.'};
 }
 const byYear=generationByYear(year,input?.region);
 if(byYear)return {status:'estimated',game:'pokemon',...byYear,expansion_code:'',regulation_mark:'',year,confidence:.58,confidence_level:'low',evidence_count:1,context_evidence_count:0,basis:[`©/제작연도 ${year}`],note:'연도만 확인되어 세대/시리즈는 보조 추정입니다.'};
 if(year&&year<2007)return {status:'legacy',game:'pokemon',generation:null,generation_label:'고전 카드',series:'초기~ADV/PCG 계열',era:'LEGACY',expansion_code:'',regulation_mark:'',year,confidence:.55,confidence_level:'low',evidence_count:1,context_evidence_count:0,basis:[`©/제작연도 ${year}`],note:'고전 카드는 확장팩 코드 확인 전 세대 번호를 단정하지 않습니다.'};
 return {status:'unknown',game:'pokemon',generation:null,generation_label:'세대 확인 필요',series:'확장팩 코드·©연도 OCR 부족',era:'UNKNOWN',expansion_code:'',regulation_mark:regulation||'',year:null,confidence:0,confidence_level:'unknown',evidence_count:0,context_evidence_count:byReg?1:0,basis:byReg?[`레귤레이션 마크 ${regulation}`]:[],note:'세대 근거가 부족해 번호를 생성하지 않았습니다.'};
}

function renderPokemonGeneration(info,game='pokemon'){''',
        "generation inference",
    )

    text = replace_span(
        text,
        "function renderPokemonGeneration(info,game='pokemon'){",
        "window.TCGPokemonGeneration=Object.freeze",
        r'''function renderPokemonGeneration(info,game='pokemon'){
 const box=byId('simplePokemonGeneration');if(!box)return info;
 const isPokemon=gameName(game)==='pokemon';box.hidden=!isPokemon;if(!isPokemon)return info;
 const badge=byId('pokemonGenerationBadge'),title=byId('pokemonGenerationTitle'),meta=byId('pokemonGenerationMeta');
 if(!info||info.status==='pending'){if(badge)badge.textContent='…';if(title)title.textContent='세대 판별 중…';if(meta)meta.textContent='앞면 OCR에서 확장팩/세트 코드 · 레귤레이션 · ©연도를 확인합니다.';return info}
 if(info.status==='conflict'){if(badge)badge.textContent='!';if(title)title.textContent='세대/판본 근거 충돌';if(meta)meta.textContent=`${info.basis?.join(' · ')||'OCR 근거 충돌'} · 자동 분류 중단 · 카드번호/판본을 확인해 주세요.`;return info}
 if(info.status==='context_only'){if(badge)badge.textContent='?';if(title)title.textContent=`세대 확인 필요 · 레귤레이션 ${info.regulation_mark||''}`.trim();if(meta)meta.textContent='레귤레이션은 사용 가능 시기 표기이며 세대 번호 근거로 사용하지 않습니다. 확장팩/세트 코드 또는 ©연도를 확인해 주세요.';return info}
 if(info.status==='estimated'){if(badge)badge.textContent=info.generation_label||(`${info.generation}세대`);if(title)title.textContent=`${info.generation_label||info.generation+'세대'} · ${info.series}`;const evidence=[info.expansion_code&&`확장팩/세트 ${info.expansion_code}`,info.regulation_mark&&`레귤레이션 ${info.regulation_mark}(문맥)`,info.year&&`©${info.year}`].filter(Boolean);if(meta)meta.textContent=`${evidence.join(' · ')||info.basis?.join(' · ')||'OCR 근거'} · 신뢰도 ${info.confidence_level==='high'?'높음':info.confidence_level==='medium'?'중간(보조)':'보조'}`;return info}
 if(badge)badge.textContent=info.status==='legacy'?'고전':'?';if(title)title.textContent=info.status==='legacy'?info.generation_label:'세대 확인 필요';if(meta)meta.textContent=info.status==='legacy'?`${info.series}${info.year?' · ©'+info.year:''} · 확장팩 코드 확인 권장`:'확장팩/세트 코드·©연도를 충분히 읽지 못했습니다.';return info
}
window.TCGPokemonGeneration=Object.freeze''',
        "generation render",
    )
    text = replace_once(text, "window.TCGPokemonGeneration=Object.freeze({version:'v315'", "window.TCGPokemonGeneration=Object.freeze({version:'v320'", "generation version")

    text = replace_span(
        text,
        "function updateGenerationForCandidate(row){",
        "async function recognize(game){",
        r'''function updateGenerationForCandidate(row){
 const game=gameName(window.tcgIdentityGame||'pokemon');
 const info=inferPokemonGeneration({game,ocr_text:window.tcgIdentityOcrText||'',card_name:row?.card_name||'',card_number:row?.card_number||'',market_key:row?.market_key||'',region:byId('identityRegion')?.value||'UNKNOWN'});
 renderPokemonGeneration(info,game);window.tcgPokemonGeneration=info;return info;
}
function displayCandidates(rows,opts={}){const select=byId('identityCandidates');select.innerHTML='';select._rows=rows;if(!rows.length){select.append(new Option('일치 후보 없음 · 직접 확인 입력',''));updateGenerationForCandidate(null);return}if(opts.autoApply===false){select.append(new Option('후보가 겹칩니다 · 직접 선택해 확인',''));rows.forEach((row,index)=>{const region=REGION_CODES.has(String(row.region||'').toUpperCase())?` · ${String(row.region).toUpperCase()}`:'';select.append(new Option(`${Math.round(Number(row.confidence)*100)}% · ${row.card_name}${row.card_number?' · '+row.card_number:''}${region}`,String(index))});select.value='';updateGenerationForCandidate(null);return}rows.forEach((row,index)=>{const region=REGION_CODES.has(String(row.region||'').toUpperCase())?` · ${String(row.region).toUpperCase()}`:'';select.append(new Option(`${Math.round(Number(row.confidence)*100)}% · ${row.card_name}${row.card_number?' · '+row.card_number:''}${region}`,String(index))});select.value='0';applyCandidate(rows[0],opts)}
function applyCandidate(row,opts={}){if(!row){updateGenerationForCandidate(null);return}const current=normalizeRegion(byId('identityRegion')?.value||'UNKNOWN'),candidateRegion=normalizeRegion(row.region),allowRegionAutofill=opts.allowRegionAutofill===true;if(byId('identityCardName'))byId('identityCardName').value=safeText(row.card_name);if(byId('identityCardNumber'))byId('identityCardNumber').value=safeText(row.card_number);if(allowRegionAutofill&&current==='UNKNOWN'&&candidateRegion!=='UNKNOWN'&&byId('identityRegion'))byId('identityRegion').value=candidateRegion;const effective=normalizeRegion(byId('identityRegion')?.value||'UNKNOWN'),marketLinkBlocked=opts.marketLinkBlocked===true||effective==='UNKNOWN'||(candidateRegion!=='UNKNOWN'&&effective!==candidateRegion);if(byId('identityMarketKey'))byId('identityMarketKey').value=marketLinkBlocked?'':safeText(row.market_key);updateGenerationForCandidate(row)}
async function recognize(game){''',
        "candidate application",
    )

    text = replace_span(
        text,
        "async function recognize(game){",
        "function identityCoreKey(item){",
        r'''async function recognize(game){
 const resolvedGame=gameName(game);window.tcgIdentityGame=resolvedGame;renderPokemonGeneration({status:'pending'},resolvedGame);
 const file=window.tcgCardInputFile?.('front');if(!file){byId('identityStatus').textContent='앞면 사진이 없어 카드명을 인식할 수 없습니다.';updateGenerationForCandidate(null);return null}
 const status=byId('identityStatus');status.textContent='🔎 카드명·카드번호·판본·포켓몬 세대 자동 인식 중…';
 try{
  const [{hash,data},text]=await Promise.all([imageArtifacts(file),browserText(file)]);window.tcgIdentityImageHash=hash;
  const selected=normalizeRegion(byId('identityRegion')?.value||'UNKNOWN'),browserRegion=inferEditionFromText(text),requestRegion=selected!=='UNKNOWN'?selected:browserRegion.region;
  const browserConflict=browserRegion.conflict===true||(selected!=='UNKNOWN'&&browserRegion.region!=='UNKNOWN'&&selected!==browserRegion.region);
  let candidates=learnedCandidates(hash,resolvedGame,requestRegion),server=null;
  async function request(region){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),120000);try{const response=await fetch('/api/recognize-card',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({game:resolvedGame,region,image_hash:hash,image_data:data,ocr_text:text}),signal:controller.signal,cache:'no-store'});const payload=await response.json().catch(()=>null);return response.ok?payload:null}catch(_){return null}finally{clearTimeout(timer)}}
  server=await request(requestRegion);
  if(server?.image_hash)window.tcgIdentityImageHash=server.image_hash;
  const identityConflict=browserConflict||server?.region_conflict===true;
  const identityAmbiguous=server?.identity_ambiguous===true||server?.region_ambiguous===true||server?.market_ambiguous===true;
  if(server&&!identityConflict)candidates=mergeCandidates([...candidates,...(server.candidates||[])]);
  let detected=inferEditionFromText(server?.ocr_text||text),effectiveRegion=selected!=='UNKNOWN'?selected:(browserRegion.region!=='UNKNOWN'?browserRegion.region:detected.region);
  if(identityConflict){
   window.tcgIdentityOcrText=generationText(server?.ocr_text||text);
   candidates=[];effectiveRegion='UNKNOWN';
   if(byId('identityRegion'))byId('identityRegion').value='UNKNOWN';
   if(byId('identityCardName'))byId('identityCardName').value='';
   if(byId('identityCardNumber'))byId('identityCardNumber').value='';
   if(byId('identityMarketKey'))byId('identityMarketKey').value='';
   displayCandidates([]);updateGenerationForCandidate(null);
   status.textContent='⚠️ 한판·일판·영판 근거가 충돌해 자동 카드 선택·세대·시세 연결을 중단했습니다. 판본과 카드번호를 직접 확인해 주세요.';
   return {hash:window.tcgIdentityImageHash,candidates:[],generation:null,region:'UNKNOWN',region_conflict:true};
  }
  if(effectiveRegion!=='UNKNOWN')candidates=filterCandidatesByRegion(candidates,effectiveRegion);
  if(selected==='UNKNOWN'&&requestRegion==='UNKNOWN'&&effectiveRegion!=='UNKNOWN'){
   const retry=await request(effectiveRegion);if(retry){server=retry;if(retry.image_hash)window.tcgIdentityImageHash=retry.image_hash;candidates=filterCandidatesByRegion(mergeCandidates([...candidates,...(retry.candidates||[])]),effectiveRegion);detected=inferEditionFromText(retry.ocr_text||server?.ocr_text||text)}
  }
  window.tcgIdentityOcrText=generationText(server?.ocr_text||text);
  if(selected==='UNKNOWN'&&effectiveRegion!=='UNKNOWN'&&byId('identityRegion'))byId('identityRegion').value=effectiveRegion;
  const marketLinkBlocked=server?.market_link_blocked===true||effectiveRegion==='UNKNOWN';
  if(identityAmbiguous){
   if(byId('identityCardName'))byId('identityCardName').value='';if(byId('identityCardNumber'))byId('identityCardNumber').value='';if(byId('identityMarketKey'))byId('identityMarketKey').value='';
   displayCandidates(candidates,{autoApply:false,marketLinkBlocked:true});
   status.textContent='⚠️ 카드/판본 후보가 근접해 자동 선택과 시세 연결을 중단했습니다. 후보를 직접 선택하고 카드번호·판본을 확인해 주세요.';
   return {hash:window.tcgIdentityImageHash,candidates,generation:null,region:effectiveRegion,identity_ambiguous:true,market_link_blocked:true};
  }
  displayCandidates(candidates,{marketLinkBlocked});const best=candidates[0],generation=updateGenerationForCandidate(best||null);
  if(best){const diag=server?.ocr_diagnostics||{},passes=Number(diag.pass_count||0),stages=Array.isArray(diag.stages_completed)?diag.stages_completed:[],cross=diag.cross_validation?.cross_validated===true,edition=normalizeRegion(byId('identityRegion')?.value||'UNKNOWN');status.textContent=`✅ 후보 ${Math.round(best.confidence*100)}%${edition!=='UNKNOWN'?' · 판본 '+edition:' · 판본 확인 필요'} · OCR ${stages.length===3?'1차 전체→2차 4분할→3차 8분할 완료':stages.length+'단계'}${passes?' · '+passes+'영역':''}${cross?' · 교차검증 일치':''}${resolvedGame==='pokemon'&&generation?.status==='estimated'?' · '+generation.generation_label:''}${marketLinkBlocked?' · 시세 자동연결 보류':''} · 자동 추정값은 아래에서 확인해야 학습됩니다.`}
  else if(['tesseract_not_installed','dependency_not_installed'].includes(server?.ocr_error)){status.textContent='OCR 구성요소가 없어 자동 문자 인식을 못했습니다. 판본·카드명·번호를 확인 저장하면 이후 동일 카드 재인식에 학습됩니다.'}
  else{status.textContent='일치 후보를 찾지 못했습니다. 판본·카드명·번호를 확인 입력한 뒤 학습해 주세요.'}
  return {hash:window.tcgIdentityImageHash,candidates,generation,region:normalizeRegion(byId('identityRegion')?.value||'UNKNOWN'),market_link_blocked:marketLinkBlocked}
 }catch(_){status.textContent='카드 문자 인식 중 오류가 발생했습니다. 카드 전체가 선명한 앞면 사진인지 확인해 주세요.';updateGenerationForCandidate(null);return null}
}
function identityCoreKey(item){''',
        "browser recognition",
    )

    text = replace_once(
        text,
        "select.addEventListener('change',()=>applyCandidate(select._rows?.[Number(select.value)]));",
        "select.addEventListener('change',()=>applyCandidate(select._rows?.[Number(select.value)],{allowRegionAutofill:true}));",
        "manual candidate selection",
    )
    write(path, text)


def patch_market_linking() -> None:
    path = "grade_market_flow.js"
    text = read(path)
    text = replace_once(
        text,
        "function matchingPlatformQuotes(name,number,region){\n const all=platformMarket?.platform_quotes?.WYYYES;",
        "function matchingPlatformQuotes(name,number,region){\n if(editionCode(region)==='UNKNOWN')return [];\n const all=platformMarket?.platform_quotes?.WYYYES;",
        "platform quote edition gate",
    )
    text = replace_once(
        text,
        " const name=(el('identityCardName')?.value||'').trim(),number=(el('identityCardNumber')?.value||'').trim(),region=(el('identityRegion')?.value||'').trim();\n if(!name&&!number){box.textContent='카드 인식 후 판본별 자동수집 공개시장 자료를 연결합니다.';renderReferenceSources();return}\n if(!platformLoaded)",
        " const name=(el('identityCardName')?.value||'').trim(),number=(el('identityCardNumber')?.value||'').trim(),region=(el('identityRegion')?.value||'').trim();\n if(!name&&!number){box.textContent='카드 인식 후 판본별 자동수집 공개시장 자료를 연결합니다.';renderReferenceSources();return}\n if(editionCode(region)==='UNKNOWN'){box.textContent='판본 확인 후 동일 판본 시세만 연결합니다.';renderReferenceSources();return}\n if(!platformLoaded)",
        "render quote edition gate",
    )
    text = replace_once(
        text,
        " const wanted=editionCode(region),options=[...select.options].filter(option=>option.value);\n const n=norm(name)",
        " const wanted=editionCode(region),options=[...select.options].filter(option=>option.value);\n if(wanted==='UNKNOWN')return '';\n const n=norm(name)",
        "saved market edition gate",
    )
    write(path, text)


def patch_generation_tests() -> None:
    path = "verify_pokemon_generation_runtime.js"
    text = read(path)
    text = replace_once(
        text,
        "r=api.infer({game:'pokemon',ocr_text:'REGULATION MARK H'});\neq(r.generation,9,'reg H generation');eq(r.regulation_mark,'H','reg H mark');eq(r.confidence_level,'medium','reg H confidence');ok(/보조/.test(r.note),'regulation must be advisory');",
        "r=api.infer({game:'pokemon',ocr_text:'REGULATION MARK H'});\neq(r.generation,null,'reg H must not invent generation');eq(r.regulation_mark,'H','reg H mark');eq(r.status,'context_only','reg H context status');eq(r.confidence_level,'context','reg H context confidence');ok(/세대 번호로 변환하지/.test(r.note),'regulation must remain context only');",
        "reg H test",
    )
    text = replace_once(
        text,
        "r=api.infer({game:'pokemon',card_number:'PAL185/193',region:'US',regulation_mark:'F'});\neq(r.status,'conflict','set generation vs regulation generation must conflict');eq(r.generation,null,'generation evidence conflict must fail closed');",
        "r=api.infer({game:'pokemon',card_number:'PAL185/193',region:'US',regulation_mark:'F'});\neq(r.status,'estimated','regulation context must not override exact set generation');eq(r.generation,9,'set code remains generation evidence');eq(r.context_evidence_count,1,'regulation recorded as context');",
        "set regulation semantics test",
    )
    text = replace_once(
        text,
        "r=api.infer({game:'pokemon',card_number:'PAL185/193',region:'US',regulation_mark:'H',ocr_text:'©2024 Pokémon'});\neq(r.generation,9,'three-evidence generation');ok(r.evidence_count>=3,'three independent generation evidence');ok(r.basis.some(x=>x.includes('©/제작연도')),'year evidence retained');",
        "r=api.infer({game:'pokemon',card_number:'PAL185/193',region:'US',regulation_mark:'H',ocr_text:'©2024 Pokémon'});\neq(r.generation,9,'set+year generation');eq(r.evidence_count,2,'only set and year count as generation evidence');eq(r.context_evidence_count,1,'regulation is context evidence');ok(r.basis.some(x=>x.includes('©/제작연도')),'year evidence retained');",
        "generation evidence count test",
    )
    text = replace_once(text, "eq(api.version,'v315','generation runtime version');\nconsole.log('Pokémon generation runtime v315: PASS');", "eq(api.version,'v320','generation runtime version');\nconsole.log('Pokémon generation runtime v320: PASS');", "runtime version test")
    write(path, text)

    path = "test_card_edition_precision_v302.py"
    text = read(path)
    text = replace_once(
        text,
        '            self.assertEqual("estimated", result["status"])\n            self.assertEqual(9, result["generation"])\n            self.assertEqual("medium", result["confidence_level"])\n            self.assertAlmostEqual(0.72, float(result["confidence"]), places=6)',
        '            self.assertEqual("context_only", result["status"])\n            self.assertIsNone(result["generation"])\n            self.assertEqual("context", result["confidence_level"])\n            self.assertEqual(0, result["evidence_count"])\n            self.assertEqual(1, result["context_evidence_count"])',
        "v302 regulation test",
    )
    write(path, text)

    path = "test_card_region_generation_precision_v306.py"
    text = read(path)
    text = replace_once(text, "Pokémon generation runtime v315: PASS", "Pokémon generation runtime v320: PASS", "v306 runtime expectation")
    write(path, text)


def patch_runtime_verifier() -> None:
    path = "verify_current_runtime.py"
    text = read(path)
    text = replace_once(
        text,
        '       "test_card_identity_market_precision_v309.py","test_card_region_conflict_failclosed_v318.py",\n       "test_multi_market_price_collector.py"',
        '       "test_card_identity_market_precision_v309.py","test_card_region_conflict_failclosed_v318.py",\n       "test_card_identity_ambiguity_v320.py","test_multi_market_price_collector.py"',
        "static v320 test registration",
    )
    text = replace_once(
        text,
        '                  "test_card_identity_market_precision_v309.py","test_card_region_conflict_failclosed_v318.py"],360,False),',
        '                  "test_card_identity_market_precision_v309.py","test_card_region_conflict_failclosed_v318.py",\n                  "test_card_identity_ambiguity_v320.py"],360,False),',
        "node v320 test registration",
    )
    text = replace_once(text, '"engine":"current-main-v318-card-region-conflict-failclosed"', '"engine":"current-main-v320-card-identity-market-failclosed"', "runtime engine")
    write(path, text)


def main() -> None:
    patch_server_identity()
    patch_browser_identity()
    patch_market_linking()
    patch_generation_tests()
    patch_runtime_verifier()
    print("card identity / edition / generation / market precision v320 patch applied")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


path = "card_identity_recognition.py"
src = read(path)
src = replace_once(
    src,
    "from safe_runtime import atomic_write_json, safe_read_text",
    "from safe_runtime import atomic_write_json, exclusive_file_lock, safe_read_text",
    label="safe_runtime import",
)
src = replace_once(
    src,
    '''    if hangul >= 2 and hangul >= kana:
        return "KR"
    if kana >= 2:
        return "JP"
''',
    '''    # Mixed strong scripts are conflicting edition evidence. Do not pick a
    # region by character-count tie breaking; require user/catalog confirmation.
    if hangul >= 2 and kana >= 2:
        return "UNKNOWN"
    if hangul >= 2:
        return "KR"
    if kana >= 2:
        return "JP"
''',
    label="server mixed script region",
)
src = replace_once(
    src,
    '''    preferred = ["eng"]
    region = normalize_region(region)
    if region == "KR":
        preferred.append("kor")
    elif region == "JP":
        preferred.append("jpn")
    elif multilingual_fallback:
        preferred.extend(("kor", "jpn"))
''',
    '''    region = normalize_region(region)
    if region == "KR":
        preferred = ["kor", "eng"]
    elif region == "JP":
        preferred = ["jpn", "eng"]
    else:
        preferred = ["eng"]
        if multilingual_fallback:
            preferred.extend(("kor", "jpn"))
''',
    label="ocr language order",
)

start = src.index("def match_learning(")
end = src.index("\n\ndef recognize(", start)
new_match = '''def match_learning(image_hash: str, game: str, region: str = "UNKNOWN") -> list[dict[str, Any]]:
    if not HASH_RE.fullmatch(image_hash or ""):
        return []
    requested_region = normalize_region(region)

    def region_matches(row: dict[str, Any]) -> bool:
        row_region = normalize_region(row.get("region"))
        return requested_region == "UNKNOWN" or row_region == requested_region

    rows = [
        row for row in learning_payload().get("confirmed", [])
        if isinstance(row, dict) and row.get("game") == game and region_matches(row)
    ]
    # Similar-image support is counted inside one exact edition only.
    identities = Counter(
        (
            row.get("card_name"),
            row.get("card_number"),
            row.get("market_key"),
            normalize_region(row.get("region")),
        )
        for row in rows
    )
    hits = []
    for row in rows:
        stored = str(row.get("image_hash") or "")
        if not HASH_RE.fullmatch(stored):
            continue
        distance = _hamming(image_hash, stored)
        identity = (
            row.get("card_name"),
            row.get("card_number"),
            row.get("market_key"),
            normalize_region(row.get("region")),
        )
        exact = distance == 0
        if exact or (distance <= 8 and identities[identity] >= 3):
            hits.append({
                "market_key": row.get("market_key", ""), "region": row.get("region", "UNKNOWN"),
                "game": row.get("game", game), "card_name": row.get("card_name", ""),
                "card_number": row.get("card_number", ""),
                "confidence": 0.999 if exact else round(max(0.86, 0.98 - distance * 0.012), 4),
                "matched_by": "confirmed_exact_image" if exact else "confirmed_visual_learning",
            })
    unique = {}
    for row in hits:
        key = (row["card_name"], row["card_number"], row["market_key"], normalize_region(row.get("region")))
        if key not in unique or row["confidence"] > unique[key]["confidence"]:
            unique[key] = row
    return sorted(unique.values(), key=lambda row: -row["confidence"])[:5]
'''
src = src[:start] + new_match + src[end:]

src = replace_once(
    src,
    '''    if region == "UNKNOWN":
        inferred_region = infer_region_from_text(supplied_text)
        if inferred_region != "UNKNOWN":
            region = inferred_region
    elif not HASH_RE.fullmatch(image_hash):
        raise ValueError("이미지 또는 특징값 필요")
    learned = match_learning(image_hash, game, region)
''',
    '''    inferred_region = infer_region_from_text(supplied_text)
    region_conflict = (
        region in {"KR", "JP", "US"}
        and inferred_region in {"KR", "JP", "US"}
        and inferred_region != region
    )
    if region == "UNKNOWN" and inferred_region != "UNKNOWN":
        region = inferred_region
    elif region != "UNKNOWN" and not HASH_RE.fullmatch(image_hash):
        raise ValueError("이미지 또는 특징값 필요")
    learned = match_learning(image_hash, game, region)
''',
    label="recognize region conflict",
)
src = replace_once(
    src,
    '''        "ok": True, "game": game, "region_hint": region, "image_hash": image_hash, "ocr_text": supplied_text,
        "ocr_error": ocr_error, "ocr_diagnostics": ocr_diagnostics,
''',
    '''        "ok": True, "game": game, "region_hint": region, "inferred_region": inferred_region,
        "region_conflict": region_conflict, "image_hash": image_hash, "ocr_text": supplied_text,
        "ocr_error": ocr_error, "ocr_diagnostics": ocr_diagnostics,
''',
    label="recognize response conflict fields",
)

start = src.index("def save_confirmation(")
end = src.index("\n\ndef self_test(", start)
new_save = '''def save_confirmation(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("confirmed") is not True:
        raise ValueError("사용자 확인 필요")
    image_hash = str(payload.get("image_hash") or "").lower()
    if not HASH_RE.fullmatch(image_hash):
        raise ValueError("이미지 특징값 오류")
    game = normalize_game(payload.get("game"))
    if game not in GAMES:
        raise ValueError("게임 구분 오류")
    try:
        card_name = normalize_card_name(payload.get("card_name"))
    except (TypeError, ValueError) as exc:
        raise ValueError("카드명 오류") from exc
    if not card_name or len(card_name) > 120:
        raise ValueError("카드명 오류")
    card_number = normalize_number(payload.get("card_number"))
    market_key = str(payload.get("market_key") or "")
    known = {row["market_key"]: row for row in catalog()}
    if market_key and market_key not in known:
        raise ValueError("시세 키 오류")
    incoming_region = normalize_region(
        payload.get("region") or (known.get(market_key) or {}).get("region") or "UNKNOWN"
    )
    core_identity = (card_name, card_number, market_key, game)

    with exclusive_file_lock(LEARNING, timeout_seconds=10.0, stale_seconds=300.0):
        data = learning_payload()
        confirmed = [row for row in data.get("confirmed", []) if isinstance(row, dict)]
        effective_region = incoming_region
        conflicting = False

        for item in confirmed:
            if item.get("image_hash") != image_hash:
                continue
            item_core = (
                item.get("card_name"),
                item.get("card_number"),
                item.get("market_key"),
                item.get("game"),
            )
            if item_core != core_identity:
                conflicting = True
                break
            old_region = normalize_region(item.get("region"))
            if old_region in {"KR", "JP", "US"} and incoming_region in {"KR", "JP", "US"} and old_region != incoming_region:
                conflicting = True
                break
            if old_region in {"KR", "JP", "US"} and incoming_region == "UNKNOWN":
                effective_region = old_region

        if conflicting:
            conflict = {
                "image_hash": image_hash, "card_name": card_name, "card_number": card_number,
                "market_key": market_key, "game": game, "region": incoming_region,
                "reason": "same_image_conflicting_identity_or_edition",
            }
            data["conflicts"] = (list(data.get("conflicts", [])) + [conflict])[-200:]
            atomic_write_json(LEARNING, data, suffix=".identity.tmp")
            return {"ok": False, "conflict": True, "saved": False}

        promoted = False
        if effective_region in {"KR", "JP", "US"}:
            for item in confirmed:
                item_core = (
                    item.get("card_name"),
                    item.get("card_number"),
                    item.get("market_key"),
                    item.get("game"),
                )
                if (
                    item.get("image_hash") == image_hash
                    and item_core == core_identity
                    and normalize_region(item.get("region")) == "UNKNOWN"
                ):
                    item["region"] = effective_region
                    promoted = True

        identity = (*core_identity, effective_region)
        keys = {
            (
                item.get("image_hash"), item.get("card_name"), item.get("card_number"),
                item.get("market_key"), item.get("game"), normalize_region(item.get("region")),
            )
            for item in confirmed
        }
        if (image_hash, *identity) not in keys:
            confirmed.append({
                "image_hash": image_hash, "card_name": card_name, "card_number": card_number,
                "market_key": market_key, "game": game, "region": effective_region, "confirmed": True,
            })
        data["confirmed"] = confirmed[-MAX_ROWS:]
        data.update({"version": 1, "confirmed_only": True, "auto_prediction_learning": False})
        atomic_write_json(LEARNING, data, suffix=".identity.tmp")
        count = sum(
            1 for item in data["confirmed"]
            if (
                item.get("card_name"), item.get("card_number"), item.get("market_key"),
                item.get("game"), normalize_region(item.get("region")),
            ) == identity
        )
        return {
            "ok": True, "saved": True, "promoted_region": promoted,
            "region": effective_region, "identity_confirmations": count,
            "similar_image_learning_enabled": count >= 3,
        }
'''
src = src[:start] + new_save + src[end:]
write(path, src)

path = "card_identity_recognition.js"
src = read(path)
src = replace_once(
    src,
    " if(hangul>=2&&hangul>=kana)return {region:'KR',confidence:.96,basis:'hangul_script'};\n if(kana>=2)return {region:'JP',confidence:.96,basis:'kana_script'};",
    " if(hangul>=2&&kana>=2)return {region:'UNKNOWN',confidence:0,basis:'mixed_script_conflict'};\n if(hangul>=2)return {region:'KR',confidence:.96,basis:'hangul_script'};\n if(kana>=2)return {region:'JP',confidence:.96,basis:'kana_script'};",
    label="browser mixed script region",
)
start = src.index("function inferPokemonGeneration(input={}){")
end = src.index("\nfunction renderPokemonGeneration", start)
new_infer = r'''function generationConflict(inputRegion,byExpansion,expansion,regulation,byReg){
 const setRegion=normalizeRegion(byExpansion?.set_region||'UNKNOWN');
 if(inputRegion!=='UNKNOWN'&&setRegion!=='UNKNOWN'&&inputRegion!==setRegion){
  return {status:'conflict',game:'pokemon',generation:null,generation_label:'근거 충돌',series:'판본/세트코드 재확인',era:'CONFLICT',expansion_code:expansion||'',regulation_mark:regulation||'',year:null,confidence:0,confidence_level:'conflict',basis:[`선택 판본 ${inputRegion}`,`세트코드 판본 ${setRegion}`],note:'판본과 세트코드 근거가 충돌해 세대를 단정하지 않았습니다.'};
 }
 if(byExpansion&&byReg&&Number.isInteger(byExpansion.generation)&&Number.isInteger(byReg.generation)&&byExpansion.generation!==byReg.generation){
  return {status:'conflict',game:'pokemon',generation:null,generation_label:'근거 충돌',series:'세트코드/레귤레이션 재확인',era:'CONFLICT',expansion_code:expansion||'',regulation_mark:regulation||'',year:null,confidence:0,confidence_level:'conflict',basis:[`세트코드 ${expansion}`,`레귤레이션 ${regulation}`],note:'세트코드와 레귤레이션 근거가 서로 다른 세대를 가리켜 단정하지 않았습니다.'};
 }
 return null;
}
function inferPokemonGeneration(input={}){
 const game=String(input.game||'pokemon').trim().toLowerCase();
 if(game!=='pokemon')return {status:'not_applicable',game,generation:null,confidence:0,basis:[]};
 const text=[input.ocr_text,input.card_name,input.market_key].map(generationText).filter(Boolean).join(' ');
 const inputRegion=normalizeRegion(input?.region);
 const expansion=expansionFromCardNumber(input.card_number)||expansionFromOcr(text);
 const byExpansion=generationBySetCode(expansion);
 const regulation=regulationFromEvidence(input,text),byReg=generationByRegulation(regulation);
 const conflict=generationConflict(inputRegion,byExpansion,expansion,regulation,byReg);
 if(conflict){conflict.year=yearFromEvidence(input,text);return conflict}
 if(byExpansion)return {status:'estimated',game:'pokemon',...byExpansion,expansion_code:expansion,regulation_mark:regulation||'',year:yearFromEvidence(input,text),confidence:.98,confidence_level:'high',basis:[`확장팩/세트 코드 ${expansion}`],note:byExpansion.era==='MEGA'?'MEGA는 별도 TCG 시리즈/블록이므로 TCG 시리즈와 포켓몬 세대 번호를 분리해 표시합니다.':'확장팩/세트 코드 기준 추정'};
 if(byReg)return {status:'estimated',game:'pokemon',...byReg,expansion_code:'',regulation_mark:regulation,year:yearFromEvidence(input,text),confidence:.72,confidence_level:'medium',basis:[`레귤레이션 마크 ${regulation}`],note:'레귤레이션 마크는 대회 사용 가능성 표기이며 세대/시리즈는 보조 추정입니다.'};
 const year=yearFromEvidence(input,text),byYear=generationByYear(year,input?.region);
 if(byYear)return {status:'estimated',game:'pokemon',...byYear,expansion_code:'',regulation_mark:'',year,confidence:.58,confidence_level:'low',basis:[`©/제작연도 ${year}`],note:'연도만 확인되어 세대/시리즈는 보조 추정입니다.'};
 if(year&&year<2007)return {status:'legacy',game:'pokemon',generation:null,generation_label:'고전 카드',series:'초기~ADV/PCG 계열',era:'LEGACY',expansion_code:'',regulation_mark:'',year,confidence:.55,confidence_level:'low',basis:[`©/제작연도 ${year}`],note:'고전 카드는 확장팩 코드 확인 전 세대 번호를 단정하지 않습니다.'};
 return {status:'unknown',game:'pokemon',generation:null,generation_label:'세대 확인 필요',series:'확장팩 코드·레귤레이션·©연도 OCR 부족',era:'UNKNOWN',expansion_code:'',regulation_mark:'',year:null,confidence:0,confidence_level:'unknown',basis:[],note:'근거가 부족해 세대를 생성하지 않았습니다.'};
}'''
src = src[:start] + new_infer + src[end:]
start = src.index("function renderPokemonGeneration(info,game='pokemon'){")
end = src.index("\nwindow.TCGPokemonGeneration=", start)
old_render = src[start:end]
new_render = old_render.replace(
    " if(info.status==='estimated'){",
    " if(info.status==='conflict'){if(badge)badge.textContent='!';if(title)title.textContent='세대/판본 근거 충돌';if(meta)meta.textContent=`${info.basis?.join(' · ')||'OCR 근거 충돌'} · 자동 분류 중단 · 카드번호/판본을 확인해 주세요.`;return info}\n if(info.status==='estimated'){",
    1,
)
src = src[:start] + new_render + src[end:]
src = replace_once(
    src,
    "window.TCGPokemonGeneration=Object.freeze({version:'v306',infer:inferPokemonGeneration,render:renderPokemonGeneration,inferRegion:inferEditionFromText});",
    "window.TCGPokemonGeneration=Object.freeze({version:'v309',infer:inferPokemonGeneration,render:renderPokemonGeneration,inferRegion:inferEditionFromText});",
    label="generation api version",
)
old_learned = "function learnedCandidates(hash,game){const rows=localRows().filter(row=>row.game===game),counts=new Map();for(const row of rows){const key=[row.card_name,row.card_number,row.market_key,row.region||'UNKNOWN'].join('|');counts.set(key,(counts.get(key)||0)+1)}const hits=[];for(const row of rows){const distance=hamming(hash,row.image_hash),key=[row.card_name,row.card_number,row.market_key,row.region||'UNKNOWN'].join('|');if(distance===0||(distance<=8&&(counts.get(key)||0)>=3))hits.push({...row,confidence:distance===0?.999:Math.max(.86,.98-distance*.012),matched_by:distance===0?'confirmed_exact_image':'confirmed_visual_learning'})}return hits.sort((a,b)=>b.confidence-a.confidence).slice(0,5)}"
new_learned = "function learnedCandidates(hash,game,region='UNKNOWN'){const requested=normalizeRegion(region),rows=localRows().filter(row=>row.game===game&&(requested==='UNKNOWN'||normalizeRegion(row.region)===requested)),counts=new Map();for(const row of rows){const key=[row.card_name,row.card_number,row.market_key,normalizeRegion(row.region)].join('|');counts.set(key,(counts.get(key)||0)+1)}const hits=[];for(const row of rows){const distance=hamming(hash,row.image_hash),key=[row.card_name,row.card_number,row.market_key,normalizeRegion(row.region)].join('|');if(distance===0||(distance<=8&&(counts.get(key)||0)>=3))hits.push({...row,confidence:distance===0?.999:Math.max(.86,.98-distance*.012),matched_by:distance===0?'confirmed_exact_image':'confirmed_visual_learning'})}return hits.sort((a,b)=>b.confidence-a.confidence).slice(0,5)}"
src = replace_once(src, old_learned, new_learned, label="browser learned candidate edition isolation")
src = replace_once(
    src,
    "function mergeCandidates(rows){const found=new Map();for(const row of rows.filter(Boolean)){const key=[row.card_name,row.card_number,row.market_key,row.region||'UNKNOWN'].join('|'),old=found.get(key);if(!old||Number(row.confidence)>Number(old.confidence))found.set(key,row)}return [...found.values()].sort((a,b)=>Number(b.confidence)-Number(a.confidence)).slice(0,5)}",
    "function mergeCandidates(rows){const found=new Map();for(const row of rows.filter(Boolean)){const key=[row.card_name,row.card_number,row.market_key,normalizeRegion(row.region)].join('|'),old=found.get(key);if(!old||Number(row.confidence)>Number(old.confidence))found.set(key,row)}return [...found.values()].sort((a,b)=>Number(b.confidence)-Number(a.confidence)).slice(0,5)}\nfunction filterCandidatesByRegion(rows,region){const requested=normalizeRegion(region);return requested==='UNKNOWN'?rows:rows.filter(row=>normalizeRegion(row?.region)===requested)}",
    label="browser candidate merge filter",
)
src = replace_once(src, "  let candidates=learnedCandidates(hash,resolvedGame),server=null;", "  let candidates=learnedCandidates(hash,resolvedGame,requestRegion),server=null;", label="browser learned region")
src = replace_once(
    src,
    "  let detected=inferEditionFromText(server?.ocr_text||text),effectiveRegion=selected!=='UNKNOWN'?selected:(browserRegion.region!=='UNKNOWN'?browserRegion.region:detected.region);\n  let best=candidates[0];",
    "  let detected=inferEditionFromText(server?.ocr_text||text),effectiveRegion=selected!=='UNKNOWN'?selected:(browserRegion.region!=='UNKNOWN'?browserRegion.region:detected.region);\n  if(effectiveRegion!=='UNKNOWN')candidates=filterCandidatesByRegion(candidates,effectiveRegion);\n  let best=candidates[0];",
    label="browser candidate region filter",
)
src = replace_once(
    src,
    "   const retry=await request(effectiveRegion);if(retry){server=retry;if(retry.image_hash)window.tcgIdentityImageHash=retry.image_hash;candidates=mergeCandidates([...candidates,...(retry.candidates||[])]);detected=inferEditionFromText(retry.ocr_text||server?.ocr_text||text);best=candidates[0]}",
    "   const retry=await request(effectiveRegion);if(retry){server=retry;if(retry.image_hash)window.tcgIdentityImageHash=retry.image_hash;candidates=filterCandidatesByRegion(mergeCandidates([...candidates,...(retry.candidates||[])]),effectiveRegion);detected=inferEditionFromText(retry.ocr_text||server?.ocr_text||text);best=candidates[0]}",
    label="browser retry region filter",
)
src = replace_once(src, "window.tcgCardIdentityLearning=Object.freeze({version:'v302-edition-aware-ocr-learning'", "window.tcgCardIdentityLearning=Object.freeze({version:'v309-edition-isolated-ocr-learning'", label="browser learning version")
write(path, src)

path = "grade_market_flow.js"
src = read(path)
src = replace_once(
    src,
    ''' let score=0;
 if(cn&&qcn&&cn===qcn)score+=120;
 if(n&&n.length>=4&&(title.includes(n)||n.includes(title)))score+=50;
''',
    ''' let score=0;
 if(cn){
   if(!qcn||cn!==qcn)return -999;
   score+=120;
 }
 if(n&&n.length>=4&&(title.includes(n)||n.includes(title)))score+=50;
''',
    label="platform quote exact number",
)
start = src.index("function findMarketKey(name,number,region){")
end = src.index("\nfunction applyIdentity()", start)
new_market = r'''function findMarketKey(name,number,region){
 const select=el('econCard');if(!select)return '';
 const wanted=editionCode(region),options=[...select.options].filter(option=>option.value);
 const n=norm(name),cn=norm(number),direct=(el('identityMarketKey')?.value||'').trim();
 const directOption=options.find(option=>option.value===direct);
 if(directOption&&(wanted==='UNKNOWN'||marketKeyEdition(direct)===wanted)){
   const directBlob=norm(directOption.textContent+' '+directOption.value);
   if(!cn||directBlob.includes(cn))return direct;
 }
 const ranked=[];
 for(const option of options){
   const actual=marketKeyEdition(option.value);if(wanted!=='UNKNOWN'&&actual!==wanted)continue;
   const blob=norm(option.textContent+' '+option.value);let score=0;
   if(cn&&!blob.includes(cn))continue;
   if(cn)score+=100;
   if(n&&n.length>=3&&blob.includes(n))score+=60;
   if(wanted!=='UNKNOWN'&&actual===wanted)score+=20;
   if(score>0)ranked.push({value:option.value,score});
 }
 ranked.sort((a,b)=>b.score-a.score||a.value.localeCompare(b.value));
 if(!ranked.length)return '';
 if(ranked.length>1&&ranked[0].score===ranked[1].score)return '';
 return ranked[0].value;
}'''
src = src[:start] + new_market + src[end:]
write(path, src)

path = "verify_pokemon_generation_runtime.js"
src = read(path)
marker = "\neq(api.version,'v306','generation runtime version');"
tests = r'''
region=api.inferRegion('포켓몬 카드 ポケモン カード');eq(region.region,'UNKNOWN','mixed strong scripts must not invent edition');eq(region.basis,'mixed_script_conflict','mixed script basis');

r=api.infer({game:'pokemon',card_number:'PAL185/193',region:'JP'});
eq(r.status,'conflict','English set code vs Japanese edition must conflict');eq(r.generation,null,'edition conflict must not invent generation');

r=api.infer({game:'pokemon',card_number:'PAL185/193',region:'US',regulation_mark:'F'});
eq(r.status,'conflict','set generation vs regulation generation must conflict');eq(r.generation,null,'generation evidence conflict must fail closed');
'''
src = replace_once(src, marker, tests + "\neq(api.version,'v309','generation runtime version');", label="generation runtime v309")
src = src.replace("console.log('Pokémon generation runtime v306: PASS');", "console.log('Pokémon generation runtime v309: PASS');")
write(path, src)

for path in ("test_card_edition_precision_v302.py", "test_card_region_generation_precision_v306.py"):
    src = read(path)
    src = src.replace("Pokémon generation runtime v306: PASS", "Pokémon generation runtime v309: PASS")
    write(path, src)

test = r'''from __future__ import annotations

import json
import multiprocessing as mp
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import card_identity_recognition as identity

ROOT = Path(__file__).resolve().parent


def _save_worker(path: str, payload: dict) -> None:
    import card_identity_recognition as worker_identity
    worker_identity.LEARNING = Path(path)
    result = worker_identity.save_confirmation(payload)
    if not result.get("ok"):
        raise SystemExit(2)


class CardIdentityMarketPrecisionV309Tests(unittest.TestCase):
    def payload(self, *, image_hash: str, name: str, region: str) -> dict:
        return {
            "confirmed": True, "image_hash": image_hash, "game": "pokemon",
            "card_name": name, "card_number": "", "market_key": "", "region": region,
        }

    def test_server_mixed_scripts_fail_closed(self) -> None:
        self.assertEqual("UNKNOWN", identity.infer_region_from_text("포켓몬 카드 ポケモン カード"))
        self.assertEqual("KR", identity.infer_region_from_text("포켓몬 카드 피카츄"))
        self.assertEqual("JP", identity.infer_region_from_text("ポケモンカード ピカチュウ"))

    def test_server_unknown_to_known_region_promotes_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "identity.json"
            with mock.patch.object(identity, "LEARNING", store):
                first = identity.save_confirmation(self.payload(image_hash="0000000000000001", name="Pikachu", region="UNKNOWN"))
                second = identity.save_confirmation(self.payload(image_hash="0000000000000001", name="Pikachu", region="KR"))
                self.assertTrue(first["ok"])
                self.assertTrue(second["ok"])
                self.assertTrue(second["promoted_region"])
                rows = json.loads(store.read_text(encoding="utf-8"))["confirmed"]
                self.assertEqual(1, len(rows))
                self.assertEqual("KR", rows[0]["region"])

    def test_known_region_learning_is_strictly_edition_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "identity.json"
            store.write_text(json.dumps({
                "version": 1, "conflicts": [], "confirmed": [
                    {"image_hash": "0000000000000001", "game": "pokemon", "card_name": "Pikachu", "card_number": "", "market_key": "", "region": "JP"},
                    {"image_hash": "0000000000000002", "game": "pokemon", "card_name": "Pikachu", "card_number": "", "market_key": "", "region": "JP"},
                    {"image_hash": "0000000000000004", "game": "pokemon", "card_name": "Pikachu", "card_number": "", "market_key": "", "region": "JP"},
                    {"image_hash": "0000000000000008", "game": "pokemon", "card_name": "Pikachu", "card_number": "", "market_key": "", "region": "UNKNOWN"},
                ],
            }), encoding="utf-8")
            with mock.patch.object(identity, "LEARNING", store):
                self.assertEqual([], identity.match_learning("0000000000000000", "pokemon", "KR"))
                self.assertTrue(identity.match_learning("0000000000000000", "pokemon", "JP"))

    def test_learning_transaction_preserves_parallel_distinct_confirmations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = str(Path(tmp) / "identity.json")
            ctx = mp.get_context("spawn")
            jobs = [
                ctx.Process(target=_save_worker, args=(store, self.payload(image_hash=f"{i:016x}", name=f"Card-{i}", region="KR")))
                for i in range(1, 9)
            ]
            for job in jobs:
                job.start()
            for job in jobs:
                job.join(20)
                self.assertEqual(0, job.exitcode)
            rows = json.loads(Path(store).read_text(encoding="utf-8"))["confirmed"]
            self.assertEqual(8, len(rows))
            self.assertEqual({f"Card-{i}" for i in range(1, 9)}, {row["card_name"] for row in rows})

    def test_market_number_contract_requires_exact_number(self) -> None:
        source = (ROOT / "grade_market_flow.js").read_text(encoding="utf-8")
        self.assertIn("if(!qcn||cn!==qcn)return -999", source)
        self.assertIn("if(cn&&!blob.includes(cn))continue", source)
        self.assertIn("if(!cn||directBlob.includes(cn))return direct", source)

    def test_browser_generation_conflict_contract_executes(self) -> None:
        proc = subprocess.run(
            ["node", "verify_pokemon_generation_runtime.js"], cwd=ROOT, text=True,
            capture_output=True, timeout=30, check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("Pokémon generation runtime v309: PASS", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
'''
write("test_card_identity_market_precision_v309.py", test)

path = "verify_current_runtime.py"
src = read(path)
src = replace_once(
    src,
    '"test_card_tablet_runtime_v300.py","test_card_edition_precision_v302.py","test_card_region_generation_precision_v306.py",',
    '"test_card_tablet_runtime_v300.py","test_card_edition_precision_v302.py","test_card_region_generation_precision_v306.py",\n       "test_card_identity_market_precision_v309.py",',
    label="runtime static v309",
)
src = replace_once(
    src,
    '"test_pokemon_generation_display_v207.py","test_card_edition_precision_v302.py","test_card_region_generation_precision_v306.py"],360,False),',
    '"test_pokemon_generation_display_v207.py","test_card_edition_precision_v302.py","test_card_region_generation_precision_v306.py",\n                  "test_card_identity_market_precision_v309.py"],360,False),',
    label="runtime node v309",
)
src = src.replace("current-main-v306-region-generation-precision-gated", "current-main-v309-card-identity-market-precision-gated")
write(path, src)

print("card precision v309 patch prepared")

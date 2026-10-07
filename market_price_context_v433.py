#!/usr/bin/env python3
"""V433 competitor-derived exact card/price context.

Fail-closed normalization shared by scan correction, market pricing and portfolio
surfaces. It never invents a price and never merges unlike card variants.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any

CONDITIONS=("NM","LP","MP","HP","DMG")
LANGUAGES=("KR","JP","EN","CT","CS","FR","DE","IT","PT","ES")
PRINTINGS=("normal","foil","reverse","parallel","promo","first_edition","other")
GRADERS=("RAW","PSA","BGS","CGC","TAG","BRG")

@dataclass(frozen=True)
class CardPriceIdentity:
    game:str; card_name:str; card_number:str; set_name:str
    language:str; condition:str; printing:str; grader:str="RAW"; grade:str="RAW"
    def validate(self)->tuple[bool,tuple[str,...]]:
        e=[]
        for k in ("game","card_name","card_number","set_name"):
            if not str(getattr(self,k,"")).strip(): e.append(f"{k.upper()}_MISSING")
        if self.language not in LANGUAGES:e.append("LANGUAGE_UNSUPPORTED")
        if self.condition not in CONDITIONS:e.append("CONDITION_UNSUPPORTED")
        if self.printing not in PRINTINGS:e.append("PRINTING_UNSUPPORTED")
        if self.grader not in GRADERS:e.append("GRADER_UNSUPPORTED")
        if self.grader=="RAW" and self.grade!="RAW":e.append("RAW_GRADE_MISMATCH")
        if self.grader!="RAW" and self.grade=="RAW":e.append("GRADED_GRADE_MISSING")
        return not e,tuple(e)
    def key(self)->str:
        ok,e=self.validate()
        if not ok: raise ValueError(",".join(e))
        return "|".join((self.game,self.card_number,self.set_name,self.language,self.condition,self.printing,self.grader,self.grade))

def price_freshness(source_date:str, *, today:date|None=None)->dict[str,Any]:
    today=today or datetime.now(timezone.utc).date()
    try:d=date.fromisoformat(source_date[:10])
    except (TypeError,ValueError,AttributeError):return {"status":"UNKNOWN","age_days":None,"confidence_cap":0.25}
    age=max(0,(today-d).days)
    if age<=2:return {"status":"FRESH","age_days":age,"confidence_cap":0.98}
    if age<=7:return {"status":"AGING","age_days":age,"confidence_cap":0.85}
    if age<=30:return {"status":"STALE","age_days":age,"confidence_cap":0.60}
    return {"status":"EXPIRED","age_days":age,"confidence_cap":0.35}

def price_context(identity:CardPriceIdentity, evidence:list[dict[str,Any]], *, today:date|None=None)->dict[str,Any]:
    ok,errors=identity.validate()
    if not ok:return {"status":"QUARANTINE","identity_errors":list(errors),"candidates":[]}
    accepted=[]
    for row in evidence:
        if not isinstance(row,dict) or row.get("identity_key")!=identity.key():continue
        value=row.get("price")
        if not isinstance(value,(int,float)) or value<=0:continue
        fresh=price_freshness(str(row.get("source_date") or ""),today=today)
        accepted.append({**row,"freshness":fresh})
    if not accepted:return {"status":"MISSING","identity_key":identity.key(),"candidates":[]}
    accepted.sort(key=lambda r:(-float(r["freshness"]["confidence_cap"]),-float(r["price"])))
    prices=sorted(float(r["price"]) for r in accepted)
    mid=len(prices)//2
    median=prices[mid] if len(prices)%2 else (prices[mid-1]+prices[mid])/2
    lineages={str(r.get("lineage_key") or r.get("source") or "") for r in accepted if r.get("lineage_key") or r.get("source")}
    confidence=min(min(float(r["freshness"]["confidence_cap"]) for r in accepted),0.55+0.12*min(3,len(lineages)))
    return {"status":"VERIFIED" if len(lineages)>=2 and confidence>=0.75 else "PROVISIONAL",
            "identity_key":identity.key(),"median_price":median,"evidence_count":len(accepted),
            "lineage_count":len(lineages),"confidence":round(confidence,3),"candidates":accepted}

def scan_candidates(rows:list[dict[str,Any]], *, minimum:float=.45, ambiguity_margin:float=.08)->dict[str,Any]:
    clean=[r for r in rows if isinstance(r,dict) and isinstance(r.get("score"),(int,float)) and 0<=r["score"]<=1 and r["score"]>=minimum]
    clean.sort(key=lambda r:(-r["score"],str(r.get("card_number","")),str(r.get("set_name",""))))
    if not clean:return {"status":"NO_MATCH","candidates":[],"requires_user_confirmation":True}
    margin=clean[0]["score"]-(clean[1]["score"] if len(clean)>1 else 0)
    ambiguous=len(clean)>1 and margin<ambiguity_margin
    return {"status":"AMBIGUOUS" if ambiguous else "MATCH","candidates":clean[:5],
            "requires_user_confirmation":ambiguous or clean[0]["score"]<.78,"margin":round(margin,4)}

def portfolio_position(*,quantity:int,buy_unit:float,current_unit:float,sold_quantity:int=0,sold_unit:float|None=None)->dict[str,Any]:
    if quantity<0 or sold_quantity<0 or sold_quantity>quantity or buy_unit<0 or current_unit<0:raise ValueError("invalid portfolio values")
    held=quantity-sold_quantity; cost=quantity*buy_unit; current=held*current_unit
    realized=(sold_quantity*((sold_unit if sold_unit is not None else 0)-buy_unit)) if sold_quantity else 0.0
    unrealized=held*(current_unit-buy_unit)
    return {"quantity":quantity,"held_quantity":held,"cost_basis":round(cost,2),"current_value":round(current,2),
            "realized_pnl":round(realized,2),"unrealized_pnl":round(unrealized,2),"total_pnl":round(realized+unrealized,2)}

def price_history(points:list[dict[str,Any]], *, as_of:date|None=None)->dict[str,Any]:
    """Verified daily median history and 7D/30D/90D/180D/365D momentum."""
    as_of=as_of or datetime.now(timezone.utc).date()
    daily:dict[date,list[float]]={}
    for row in points:
        if not isinstance(row,dict) or row.get("verification_status") not in {"verified","VERIFIED"}:continue
        try:d=date.fromisoformat(str(row.get("source_date") or "")[:10]);v=float(row["price"])
        except (TypeError,ValueError,KeyError):continue
        if v<=0 or d>as_of:continue
        daily.setdefault(d,[]).append(v)
    series=[]
    for d,vals in sorted(daily.items()):
        vals.sort();n=len(vals);mid=n//2;med=vals[mid] if n%2 else (vals[mid-1]+vals[mid])/2
        series.append({"date":d.isoformat(),"price":round(med,2),"samples":n})
    if not series:return {"status":"MISSING","series":[],"windows":{}}
    latest=series[-1]["price"]; windows={}
    for days,label in ((7,"7D"),(30,"30D"),(90,"3M"),(180,"6M"),(365,"1Y")):
        cutoff=as_of.toordinal()-days
        base=next((x for x in series if date.fromisoformat(x["date"]).toordinal()>=cutoff),None)
        windows[label]=None if not base or base["price"]<=0 else round((latest/base["price"]-1)*100,2)
    return {"status":"VERIFIED","latest":latest,"series":series,"windows":windows}

def price_alert(history:dict[str,Any], *, pct_threshold:float=12.0)->dict[str,Any]:
    if history.get("status")!="VERIFIED":return {"status":"NO_SIGNAL","reason":"VERIFIED_HISTORY_REQUIRED"}
    w=history.get("windows",{}); candidates=[(k,v) for k,v in w.items() if isinstance(v,(int,float))]
    if not candidates:return {"status":"NO_SIGNAL","reason":"INSUFFICIENT_HISTORY"}
    label,value=max(candidates,key=lambda kv:abs(kv[1]))
    if abs(value)<pct_threshold:return {"status":"STABLE","window":label,"change_pct":value}
    return {"status":"SURGE" if value>0 else "DROP","window":label,"change_pct":value,"requires_recheck":True}

def grading_expected_value(*,raw_price:float,grade_probabilities:dict[str,float],grade_prices:dict[str,float],
                           grading_cost:float,shipping_cost:float=0.0,selling_fee_rate:float=0.0)->dict[str,Any]:
    if min(raw_price,grading_cost,shipping_cost)<0 or not 0<=selling_fee_rate<1:raise ValueError("invalid economics")
    probs={str(k):float(v) for k,v in grade_probabilities.items() if isinstance(v,(int,float)) and v>=0}
    total=sum(probs.values())
    if total<=0:return {"status":"MISSING","reason":"GRADE_PROBABILITY_REQUIRED"}
    probs={k:v/total for k,v in probs.items()}
    missing=[g for g in probs if g not in grade_prices or not isinstance(grade_prices[g],(int,float)) or grade_prices[g]<0]
    if missing:return {"status":"MISSING","reason":"GRADE_PRICE_REQUIRED","missing_grades":missing}
    gross=sum(probs[g]*float(grade_prices[g]) for g in probs)
    net=gross*(1-selling_fee_rate)-grading_cost-shipping_cost
    incremental=net-raw_price
    roi=None if raw_price<=0 else incremental/raw_price*100
    return {"status":"VERIFIED","expected_gross":round(gross,2),"expected_net":round(net,2),
            "incremental_value":round(incremental,2),"roi_pct":None if roi is None else round(roi,2),
            "recommendation":"GRADE" if incremental>0 else "KEEP_RAW"}

def apply_scan_correction(candidate:dict[str,Any], correction:dict[str,Any])->dict[str,Any]:
    """Explicit user correction only; never silently rewrites scanner learning labels."""
    allowed={"game","card_name","card_number","set_name","language","condition","printing","grader","grade"}
    if not isinstance(candidate,dict) or not isinstance(correction,dict):raise ValueError("invalid correction")
    unknown=set(correction)-allowed
    if unknown:raise ValueError("unsupported correction fields")
    out={k:v for k,v in candidate.items() if k in allowed};out.update(correction)
    identity=CardPriceIdentity(**{k:out[k] for k in ("game","card_name","card_number","set_name","language","condition","printing","grader","grade")})
    ok,errors=identity.validate()
    if not ok:return {"status":"QUARANTINE","errors":list(errors)}
    return {"status":"CONFIRMED","identity_key":identity.key(),"identity":out,"learning_requires_verified_label":True}

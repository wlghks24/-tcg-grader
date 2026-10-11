#!/usr/bin/env python3
"""V433 competitor-derived exact card/price context.

Fail-closed normalization shared by scan correction, market pricing and portfolio
surfaces. It never invents a price and never merges unlike card variants.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import re
from urllib.parse import urlsplit

# Date-only Korean/Japanese card market observations use the KST business day.
MARKET_DAY_ZONE=timezone(timedelta(hours=9))
import math
import unicodedata
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
        for k in ("game","card_name","card_number","set_name","language","condition","printing","grader","grade"):
            if not isinstance(getattr(self,k,None),str):e.append(f"{k.upper()}_INVALID_TYPE")
        for k in ("game","card_name","card_number","set_name"):
            if not str(getattr(self,k,"")).strip(): e.append(f"{k.upper()}_MISSING")
        # The serialized key is pipe-delimited: reject embedded separators
        # instead of allowing different identities to have the same key.
        if any("|" in str(getattr(self,k,"")) for k in ("game","card_name","card_number","set_name","language","condition","printing","grader","grade")):
            e.append("IDENTITY_DELIMITER_UNSAFE")
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
        # Card name is a required part of identity, not display-only metadata.
        return "|".join((self.game,self.card_name,self.card_number,self.set_name,self.language,self.condition,self.printing,self.grader,self.grade))

def _source_market_day(value:Any)->date|None:
    """Parse only complete, bounded source days/timestamps; never trust prefixes."""
    if not isinstance(value,str):
        return None
    raw=value.strip()
    if not raw or len(raw)>96:
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}",raw):
            return date.fromisoformat(raw)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})",raw):
            timestamp=datetime.fromisoformat(raw.replace("Z","+00:00"))
            return timestamp.astimezone(MARKET_DAY_ZONE).date()
        if re.fullmatch(r"(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun), \d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4} \d{2}:\d{2}:\d{2} (?:GMT|[+-]\d{4})",raw):
            timestamp=parsedate_to_datetime(raw)
            return timestamp.astimezone(MARKET_DAY_ZONE).date() if timestamp.tzinfo else None
    except (ValueError,TypeError,OverflowError):
        return None
    return None


def price_freshness(source_date:str, *, today:date|None=None)->dict[str,Any]:
    today=today or datetime.now(MARKET_DAY_ZONE).date()
    d=_source_market_day(source_date)
    if d is None:return {"status":"UNKNOWN","age_days":None,"confidence_cap":0.25}
    if d>today:return {"status":"FUTURE","age_days":None,"confidence_cap":0.0}
    age=(today-d).days
    if age<=2:return {"status":"FRESH","age_days":age,"confidence_cap":0.98}
    if age<=7:return {"status":"AGING","age_days":age,"confidence_cap":0.85}
    if age<=30:return {"status":"STALE","age_days":age,"confidence_cap":0.60}
    return {"status":"EXPIRED","age_days":age,"confidence_cap":0.35}

PRICE_CURRENCIES=("KRW","JPY","USD")


def _reviewed_reference_proof(row:dict[str,Any], *, as_of:date|None=None)->tuple[str,str]|None:
    """A local reviewer declaration, not proof of an actual marketplace event."""
    if row.get("verification_status") not in ("verified","VERIFIED"):
        return None
    if row.get("review_status")!="manual_verified" or row.get("review_method")!="source_page_crosscheck":
        return None
    observed=_source_market_day(row.get("source_date"))
    reviewed=_source_market_day(row.get("reviewed_at"))
    if observed is None or reviewed is None or reviewed<observed or reviewed>(as_of or datetime.now(MARKET_DAY_ZONE).date()):
        return None
    if row.get("currency") not in PRICE_CURRENCIES:
        return None
    evidence_type=row.get("evidence_type")
    if evidence_type not in ("completed_sale","api_reference","market_reference"):
        return None
    lineage=row.get("lineage_key")
    source=row.get("source_url") or row.get("source")
    if not isinstance(lineage,str) or not (1<=len(lineage.strip())<=200):
        return None
    if not isinstance(source,str) or len(source)>2048:
        return None
    try:
        url=urlsplit(source)
        if url.scheme!="https" or not url.hostname or url.username or url.password or url.port not in (None,443):
            return None
        host=url.hostname.lower()
        if host=="localhost" or host.endswith((".local",".internal")) or not re.fullmatch(r"[a-z0-9.-]+",host):
            return None
        if evidence_type=="completed_sale":
            if row.get("transaction_finality") not in ("sold","completed","ended_sold","auction_sold"):
                return None
            if host not in ("ebay.com","www.ebay.com","ebay.co.jp","www.ebay.co.jp"):
                return None
            item=re.fullmatch(r"/itm/(?:[^/]+/)?([0-9]{9,14})/?",url.path)
            if item is None or row.get("sale_id")!="ebay:"+item.group(1):
                return None
        # Do not treat tracking parameters as separate independent events.
        return lineage.strip(),f"https://{host}{url.path or '/'}"
    except ValueError:
        return None


def price_context(identity:CardPriceIdentity, evidence:list[dict[str,Any]], *, today:date|None=None)->dict[str,Any]:
    ok,errors=identity.validate()
    if not ok:return {"status":"QUARANTINE","identity_errors":list(errors),"candidates":[]}
    key=identity.key()
    if not isinstance(evidence,list):return {"status":"QUARANTINE","identity_key":key,"identity_errors":["EVIDENCE_INVALID"],"candidates":[]}
    accepted=[]
    for row in evidence:
        if not isinstance(row,dict) or row.get("identity_key")!=key:continue
        if row.get("card_name") is not None and row.get("card_name")!=identity.card_name:continue
        value=row.get("price")
        if isinstance(value,bool) or not isinstance(value,(int,float)):continue
        try:numeric=float(value)
        except (TypeError,ValueError,OverflowError):continue
        if not math.isfinite(numeric) or numeric<=0:continue
        fresh=price_freshness(str(row.get("source_date") or ""),today=today)
        if fresh["status"]=="FUTURE":continue
        accepted.append({**row,"freshness":fresh})
    if not accepted:return {"status":"MISSING","identity_key":key,"candidates":[]}
    accepted.sort(key=lambda r:(-float(r["freshness"]["confidence_cap"]),-float(r["price"])))
    # Missing currency is never silently converted to KRW, and unrelated
    # currencies must never share one numeric median.
    currencies={r.get("currency") if r.get("currency") in PRICE_CURRENCIES else "UNKNOWN" for r in accepted}
    if len(currencies)>1:
        return {"status":"CURRENCY_CONFLICT","identity_key":key,"median_price":None,
                "price_currency":None,"currencies":sorted(currencies),"candidates":accepted,
                "evidence_count":len(accepted),"verified_evidence_count":0,
                "lineage_count":0,"confidence":0.0}
    price_currency=next(iter(currencies))
    reviewed=[];seen_lineages=set();seen_source_events=set()
    for row in accepted:
        proof=_reviewed_reference_proof(row,as_of=today)
        if not proof:continue
        lineage,source_event=proof
        if lineage in seen_lineages or source_event in seen_source_events:continue
        seen_lineages.add(lineage);seen_source_events.add(source_event);reviewed.append(row)
    # A completed sale and a reference quote are different populations.
    # Do not combine their prices or counts into a fictitious sale history.
    completed=[r for r in reviewed if r.get("evidence_type")=="completed_sale"]
    if completed:reviewed=completed
    else:reviewed=[r for r in reviewed if r.get("evidence_type") in ("api_reference","market_reference")]
    sample=reviewed or accepted
    prices=sorted(float(r["price"]) for r in sample)
    mid=len(prices)//2
    median=prices[mid] if len(prices)%2 else (prices[mid-1]+prices[mid])/2
    confidence=min(min(float(r["freshness"]["confidence_cap"]) for r in sample),
                   0.55+0.12*min(3,len(reviewed)))
    verified=len(reviewed)>=2 and confidence>=0.75 and price_currency!="UNKNOWN"
    basis=("reviewed_completed_sale" if completed else "reviewed_reference") if reviewed else "unreviewed_reference"
    return {"status":"VERIFIED" if verified else "PROVISIONAL",
            "identity_key":key,"median_price":median,"price_currency":price_currency,
            "evidence_count":len(accepted),"verified_evidence_count":len(reviewed),
            "lineage_count":len(reviewed),"price_basis":basis,
            "confidence":round(confidence,3),"candidates":accepted}

def scan_candidates(rows:list[dict[str,Any]], *, minimum:float=.45, ambiguity_margin:float=.08)->dict[str,Any]:
    """Rank OCR/vision suggestions without certifying an exact card or grade.

    A high image-similarity score alone is not evidence for a set, printing,
    language or condition. Those fields must not silently become market facts.
    """
    empty={"status":"NO_MATCH","candidates":[],"requires_user_confirmation":True,
           "requires_variant_confirmation":True,"match_verified":False}
    if (not isinstance(rows,list) or len(rows)>4096 or
        not _finite_nonnegative(minimum) or not 0<=minimum<=1 or
        not _finite_nonnegative(ambiguity_margin) or not 0<=ambiguity_margin<=1):
        return {**empty,"reason":"INVALID_OR_OVERSIZED_SCAN_INPUT"}
    # Check ranges BEFORE math.isfinite: huge JSON integers otherwise overflow.
    clean=[r for r in rows if isinstance(r,dict) and not isinstance(r.get("score"),bool)
           and isinstance(r.get("score"),(int,float)) and 0<=r["score"]<=1
           and math.isfinite(r["score"]) and r["score"]>=minimum]
    clean.sort(key=lambda r:(-r["score"],str(r.get("card_number","")),str(r.get("set_name",""))))
    if not clean:return {**empty,"reason":"NO_CONFIDENT_CANDIDATES"}

    def facet(row:dict[str,Any],key:str)->str:
        value=row.get(key)
        if not isinstance(value,str) or not 0<len(value.strip())<=160 or "|" in value:
            return ""
        return unicodedata.normalize("NFKC",value).strip().casefold()

    mandatory=("game","card_name","card_number","set_name","language","printing")
    # Same exact variant scanned multiple times is one candidate, not a second
    # independent hypothesis; never deduplicate candidates with missing facets.
    unique=[];seen=set()
    for row in clean:
        identified=tuple(facet(row,k) for k in mandatory)
        if all(identified):
            key=identified+(facet(row,"condition"),facet(row,"grader"),facet(row,"grade"))
            if key in seen:continue
            seen.add(key)
        unique.append(row)
    first=unique[0]
    margin=first["score"]-(unique[1]["score"] if len(unique)>1 else 0)
    # Different set/printing/language/condition can share artwork and even a
    # card number. A large confidence gap must not auto-choose that variant.
    def same_card(row):
        return all(facet(first,k) and facet(first,k)==facet(row,k)
                   for k in ("game","card_name","card_number"))
    variant_conflict=any(same_card(other) and
        any(facet(first,k)!=facet(other,k)
            for k in ("set_name","language","printing","condition"))
        for other in unique[1:])
    ambiguous=(len(unique)>1 and margin<ambiguity_margin) or variant_conflict
    variant_complete=all(facet(first,k) for k in mandatory)
    condition_confirmed=bool(facet(first,"condition"))
    return {"status":"AMBIGUOUS" if ambiguous else "MATCH",
            "candidates":unique[:5],"match_verified":False,
            "requires_variant_confirmation":not variant_complete or variant_conflict,
            "requires_condition_confirmation":not condition_confirmed,
            "requires_user_confirmation":ambiguous or first["score"]<.78 or
                  not variant_complete or not condition_confirmed,
            "margin":round(margin,4),"duplicates_removed":len(clean)-len(unique)}

def portfolio_position(*,quantity:int,buy_unit:float,current_unit:float,sold_quantity:int=0,sold_unit:float|None=None)->dict[str,Any]:
    """Calculate local collection P/L only with complete, finite transaction data."""
    if type(quantity) is not int or type(sold_quantity) is not int:
        raise ValueError("invalid portfolio quantities")
    if not (0<=sold_quantity<=quantity<=1_000_000):
        raise ValueError("invalid portfolio quantities")
    if not _finite_nonnegative(buy_unit) or not _finite_nonnegative(current_unit):
        raise ValueError("invalid portfolio prices")
    if sold_quantity and sold_unit is None:
        raise ValueError("sold_unit required for realized P/L")
    if sold_unit is not None and not _finite_nonnegative(sold_unit):
        raise ValueError("invalid sold_unit")
    held=quantity-sold_quantity
    cost=quantity*buy_unit
    current=held*current_unit
    realized=sold_quantity*(sold_unit-buy_unit) if sold_quantity else 0.0
    unrealized=held*(current_unit-buy_unit)
    result=(cost,current,realized,unrealized,realized+unrealized)
    if not all(math.isfinite(v) for v in result):
        raise ValueError("nonfinite portfolio result")
    return {"quantity":quantity,"held_quantity":held,"cost_basis":round(cost,2),"current_value":round(current,2),
            "realized_pnl":round(realized,2),"unrealized_pnl":round(unrealized,2),"total_pnl":round(realized+unrealized,2)}

def price_history(points:list[dict[str,Any]], *, as_of:date|None=None,
                  identity:CardPriceIdentity|None=None, currency:str|None=None)->dict[str,Any]:
    """Exact-card, single-currency, reviewed completed-sale history only.

    Repeated observations and listing/asking/API quotes must not fabricate a
    historical sale or an apparent 7D/30D movement.
    """
    as_of=as_of or datetime.now(MARKET_DAY_ZONE).date()
    empty={"status":"MISSING","series":[],"windows":{}}
    if not isinstance(identity,CardPriceIdentity) or not identity.validate()[0] or currency not in PRICE_CURRENCIES:
        return {**empty,"reason":"EXACT_IDENTITY_AND_CURRENCY_REQUIRED"}
    if not isinstance(points,list) or len(points)>5000:
        return {**empty,"reason":"INVALID_OR_OVERSIZED_HISTORY"}
    key=identity.key()
    exact=[r for r in points if isinstance(r,dict) and r.get("identity_key")==key
           and r.get("card_name",identity.card_name)==identity.card_name]
    # Reject rather than averaging incompatible currency values, including
    # values without a declared source currency.
    conflicting=[r for r in exact if r.get("currency")!=currency and
                 isinstance(r.get("price"),(int,float)) and not isinstance(r.get("price"),bool)]
    if conflicting:
        return {**empty,"status":"CURRENCY_CONFLICT","reason":"MIXED_OR_UNDECLARED_CURRENCY"}
    daily:dict[date,list[float]]={}
    seen_sales:set[str]=set()
    for row in exact:
        if row.get("currency")!=currency or row.get("evidence_type")!="completed_sale":
            continue
        if _reviewed_reference_proof(row,as_of=as_of) is None:
            continue
        sale_id=row.get("sale_id")
        if not isinstance(sale_id,str) or sale_id in seen_sales:
            continue
        value=row.get("price")
        if isinstance(value,bool) or not isinstance(value,(int,float)):
            continue
        d=_source_market_day(row.get("source_date"))
        if d is None or d>as_of:
            continue
        try:v=float(value)
        except (TypeError,ValueError,OverflowError):continue
        if not math.isfinite(v) or v<=0:continue
        seen_sales.add(sale_id)
        daily.setdefault(d,[]).append(v)
    series=[]
    for d,vals in sorted(daily.items()):
        vals.sort();n=len(vals);mid=n//2;med=vals[mid] if n%2 else (vals[mid-1]+vals[mid])/2
        series.append({"date":d.isoformat(),"price":round(med,2),"samples":n})
    if not series:return {**empty,"identity_key":key,"price_currency":currency,"reason":"NO_REVIEWED_COMPLETED_SALES"}
    latest=series[-1]["price"]; windows={}
    latest_day=date.fromisoformat(series[-1]["date"])
    for days,label in ((7,"7D"),(30,"30D"),(90,"3M"),(180,"6M"),(365,"1Y")):
        cutoff=as_of-timedelta(days=days)
        max_baseline_lag=max(2,min(7,days//10))
        eligible=[point for point in series[:-1]
                  if cutoff-timedelta(days=max_baseline_lag)<=date.fromisoformat(point["date"])<=cutoff]
        base=eligible[-1] if eligible else None
        windows[label]=(None if (as_of-latest_day).days>2 or base is None or base["price"]<=0
                        else round((latest/base["price"]-1)*100,2))
    return {"status":"VERIFIED","identity_key":key,"price_currency":currency,
            "evidence_type":"completed_sale","event_count":len(seen_sales),
            "latest":latest,"series":series,"windows":windows}
def price_alert(history:dict[str,Any], *, pct_threshold:float=12.0)->dict[str,Any]:
    if history.get("status")!="VERIFIED":return {"status":"NO_SIGNAL","reason":"VERIFIED_HISTORY_REQUIRED"}
    w=history.get("windows",{}); candidates=[(k,v) for k,v in w.items() if isinstance(v,(int,float))]
    if not candidates:return {"status":"NO_SIGNAL","reason":"INSUFFICIENT_HISTORY"}
    label,value=max(candidates,key=lambda kv:abs(kv[1]))
    if abs(value)<pct_threshold:return {"status":"STABLE","window":label,"change_pct":value}
    return {"status":"SURGE" if value>0 else "DROP","window":label,"change_pct":value,"requires_recheck":True}

def _finite_nonnegative(value:Any)->bool:
    if isinstance(value,bool) or not isinstance(value,(int,float)):return False
    try:
        numeric=float(value)
        return math.isfinite(numeric) and numeric>=0
    except (TypeError,ValueError,OverflowError):return False


def grading_expected_value(*,raw_price:float,grade_probabilities:dict[str,float],grade_prices:dict[str,float],
                           grading_cost:float,shipping_cost:float=0.0,selling_fee_rate:float=0.0)->dict[str,Any]:
    """Hypothetical grade economics, never a verified grade/price or profit promise.

    Inputs have no attached model-calibration or completed-sale provenance, so
    the numeric result must not be promoted to a verified recommendation.
    """
    amounts=(raw_price,grading_cost,shipping_cost,selling_fee_rate)
    if not all(_finite_nonnegative(v) for v in amounts) or not float(selling_fee_rate)<1:
        raise ValueError("invalid economics")
    if not isinstance(grade_probabilities,dict) or not grade_probabilities:
        return {"status":"MISSING","reason":"GRADE_PROBABILITY_REQUIRED"}
    if len(grade_probabilities)>20 or any(not isinstance(k,str) or not 1<=len(k)<=40 or not k.strip()
            or not _finite_nonnegative(v) or float(v)>1 for k,v in grade_probabilities.items()):
        return {"status":"MISSING","reason":"INVALID_GRADE_PROBABILITIES"}
    probs={k:float(v) for k,v in grade_probabilities.items()}
    total=sum(probs.values())
    if not math.isfinite(total) or abs(total-1.0)>1e-6:
        return {"status":"MISSING","reason":"GRADE_PROBABILITY_SUM_INVALID"}
    prices=grade_prices if isinstance(grade_prices,dict) else {}
    missing=[g for g in probs if g not in prices or not _finite_nonnegative(prices[g])]
    if missing:return {"status":"MISSING","reason":"GRADE_PRICE_REQUIRED","missing_grades":missing}
    gross=sum(probs[g]*float(prices[g]) for g in probs)
    net=gross*(1-float(selling_fee_rate))-float(grading_cost)-float(shipping_cost)
    incremental=net-float(raw_price)
    roi=None if raw_price<=0 else incremental/float(raw_price)*100
    if not all(math.isfinite(v) for v in (gross,net,incremental)) or (roi is not None and not math.isfinite(roi)):
        return {"status":"MISSING","reason":"NONFINITE_ECONOMICS"}
    return {"status":"SCENARIO","expected_gross":round(gross,2),"expected_net":round(net,2),
            "incremental_value":round(incremental,2),"roi_pct":None if roi is None else round(roi,2),
            "economic_signal":"POSITIVE" if incremental>0 else "NON_POSITIVE",
            "recommendation":"REVIEW_GRADING" if incremental>0 else "REVIEW_KEEP_RAW",
            "grade_probability_calibration_verified":False,"completed_sale_price_evidence_verified":False,
            "limitations":["GRADE_PROBABILITY_UNVERIFIED","GRADE_PRICE_SOURCE_UNVERIFIED"]}

def apply_scan_correction(candidate:dict[str,Any], correction:dict[str,Any])->dict[str,Any]:
    """Explicit user correction only; never silently rewrites scanner learning labels."""
    allowed={"game","card_name","card_number","set_name","language","condition","printing","grader","grade"}
    if not isinstance(candidate,dict) or not isinstance(correction,dict):raise ValueError("invalid correction")
    unknown=set(correction)-allowed
    if unknown:raise ValueError("unsupported correction fields")
    out={k:v for k,v in candidate.items() if k in allowed};out.update(correction)
    identity=CardPriceIdentity(**{k:out.get(k,"") for k in ("game","card_name","card_number","set_name","language","condition","printing","grader","grade")})
    ok,errors=identity.validate()
    if not ok:return {"status":"QUARANTINE","errors":list(errors)}
    return {"status":"CONFIRMED","identity_key":identity.key(),"identity":out,"learning_requires_verified_label":True}

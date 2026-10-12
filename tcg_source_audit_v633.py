#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V633: free/opt-in source-link HTTP audit + all 30-game BOX discovery plan.

Network is OFF by default. The optional probe performs at most six bounded
manufacturer GETs, does not follow redirects, and stops immediately on 429.
404/410 => review the link; 403/429/5xx => uncertain. No URL is auto-promoted.
Python 3 standard library only; no X scraping, no external paid API.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import socket
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from execution.official_box_coverage_audit_v623 import audit as audit_manufacturer_catalog

ROOT=Path(__file__).resolve().parent
REGIONS=("KR","JP","US")
MAX_PROBES=6


def safe_https(value):
    if not isinstance(value,str) or not 1<=len(value)<=1000:return False
    try:
        u=urlsplit(value)
        host=(u.hostname or "").lower()
        if not(u.scheme=="https" and host and u.username is None and u.password is None
               and u.port in (None,443) and not u.fragment):return False
        if host=="localhost" or host.endswith((".localhost",".local",".test",".invalid")):return False
        try:ipaddress.ip_address(host);return False
        except ValueError:pass
        return "." in host
    except ValueError:return False


def manufacturer_search(url,name,code="",*,engine="google"):
    if engine not in ("google","bing"):raise ValueError("UNKNOWN_SEARCH_ENGINE")
    if not safe_https(url):raise ValueError("UNSAFE_SOURCE")
    terms=["site:"+urlsplit(url).hostname]
    for value in (name,code):
        if isinstance(value,str) and 0<len(value.strip())<=180:
            terms.append('"'+value.strip().replace('"',"")+'"')
    return ("https://www.bing.com/search?" if engine=="bing" else "https://www.google.com/search?")+urlencode({"q":" ".join(terms)})


def classify(code):
    if isinstance(code,int) and 200<=code<300:return "HTTP_OK_NOT_CONTENT_VERIFIED"
    if code in (301,302,303,307,308):return "REDIRECT_REVIEW"
    if code in (404,410):return "BROKEN_LINK_REVIEW"
    if code in (401,403):return "ACCESS_RESTRICTED_UNVERIFIED"
    if code==429:return "RATE_LIMIT_PAUSE"
    if code in (408,425,500,502,503,504):return "TEMPORARY_FAILURE"
    return "NETWORK_OR_UNKNOWN_UNVERIFIED"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        return None


def probe_one(url,*,opener=None,timeout=6):
    """One bounded GET of a CURATED manufacturer URL, no body/download."""
    if not safe_https(url):return {"status":"INVALID_URL","http_status":None}
    session=opener if opener is not None else build_opener(NoRedirect())
    request=Request(url,headers={
        "User-Agent":"TCG-Grader-SourceReview/1.0 (manual opt-in; no mass crawling)",
        "Accept":"text/html,application/json;q=0.8,*/*;q=0.3",
        "Range":"bytes=0-2047"},method="GET")
    try:
        with session.open(request,timeout=timeout) as response:
            if response.geturl()!=url:
                return {"status":"REDIRECT_REVIEW","http_status":getattr(response,"status",None)}
            code=getattr(response,"status",None) or response.getcode()
            return {"status":classify(code),"http_status":code}
    except HTTPError as exc:
        output={"status":classify(exc.code),"http_status":exc.code}
        if exc.code==429 and exc.headers and exc.headers.get("Retry-After"):
            output["retry_after"]=str(exc.headers["Retry-After"])[:90]
        return output
    except (URLError,TimeoutError,socket.timeout,ssl.SSLError,OSError):
        return {"status":"NETWORK_OR_UNKNOWN_UNVERIFIED","http_status":None}


def _read(path):
    path=Path(path)
    if not path.is_file() or path.is_symlink() or path.stat().st_size>3_000_000:
        raise ValueError("MISSING_OR_LARGE_JSON")
    return json.loads(path.read_text(encoding="utf-8"))


def plan(registry,intake,base,supplement,additional=None,latest=None,newer=None,jp_proof=None,us_proof=None,jp_v659=None):
    games=registry.get("games")
    leads=intake.get("records")
    if (not isinstance(games,list) or len(games)!=30 or registry.get("schema_version")!=1 or
        not isinstance(leads,list) or len(leads)!=30 or intake.get("data_evidence_level")!="UNVERIFIED" or
        base.get("schema_version")!=1 or not isinstance(base.get("products"),list) or
        supplement.get("schema_version")!=1 or
        supplement.get("type")!="official_product_specifications_supplement" or
        supplement.get("base_catalog")!="tcg_official_product_catalog_v599.json" or
        not isinstance(supplement.get("products"),list)):
        raise ValueError("INVALID_SOURCE_INPUT")
    by_id={r["game_id"]:r for r in leads}
    if len(by_id)!=30 or len({g["id"] for g in games})!=30 or set(by_id)!={g["id"] for g in games}:
        raise ValueError("MISSING_OR_DUPLICATE_GAME")
    fields=("product_name_candidates","upcoming_name_candidates","hit_name_candidates","promo_name_candidates")
    if any(r.get("status")!="USER_SUBMITTED_UNVERIFIED" or
           any(not isinstance(r.get(k),list) for k in fields) for r in leads):
        raise ValueError("INVALID_LEAD_STATUS")
    if additional is not None and (additional.get("schema_version")!=1 or
        additional.get("type")!="official_product_specifications_supplement" or
        additional.get("base_catalog")!="tcg_official_product_catalog_v599.json" or
        additional.get("append_after")!="tcg_official_product_supplement_v630.json" or
        not isinstance(additional.get("products"),list)):
        raise ValueError("INVALID_NEW_OFFICIAL_SUPPLEMENT")
    if latest is not None and (latest.get("schema_version")!=1 or
        latest.get("type")!="official_product_specifications_supplement" or
        latest.get("base_catalog")!="tcg_official_product_catalog_v599.json" or
        latest.get("append_after")!="tcg_official_product_supplement_v636.json" or
        not isinstance(latest.get("products"),list)):
        raise ValueError("INVALID_V637_SUPPLEMENT")
    if newer is not None and (newer.get("schema_version")!=1 or
        newer.get("type")!="official_product_specifications_supplement" or
        newer.get("base_catalog")!="tcg_official_product_catalog_v599.json" or
        newer.get("append_after")!="tcg_official_product_supplement_v637.json" or
        not isinstance(newer.get("products"),list)):
        raise ValueError("INVALID_V649_SUPPLEMENT")
    if jp_proof is not None and (
        jp_proof.get("schema_version") != 1 or
        jp_proof.get("type") != "official_product_specifications_supplement" or
        jp_proof.get("base_catalog") != "tcg_official_product_catalog_v599.json" or
        jp_proof.get("append_after") != "tcg_official_product_supplement_v649.json" or
        not isinstance(jp_proof.get("products"),list)):
        raise ValueError("INVALID_V654_SUPPLEMENT")
    us_products = []
    if us_proof is not None:
        if jp_proof is None:
            raise ValueError("V657_REQUIRES_V654")
        from tcg_official_overlay_v657 import validate_overlay
        us_products = validate_overlay(us_proof, registry)
    jp_new = []
    if jp_v659 is not None:
        if us_proof is None: raise ValueError("V659_REQUIRES_V657")
        from tcg_official_overlay_v659 import validate_additions
        jp_new = validate_additions(jp_v659, registry)
    officials=base["products"]+supplement["products"]+(additional["products"] if additional else [])+(latest["products"] if latest else [])+(newer["products"] if newer else [])+(jp_proof["products"] if jp_proof else [])+us_products+jp_new
    # Apply the canonical domain, region and sealed product validation before counting.
    audit_manufacturer_catalog(registry,{"schema_version":1,"products":officials})
    if len({p["id"] for p in officials})!=len(officials):
        raise ValueError("DUPLICATE_OFFICIAL_RECORD")
    sample=Counter((p["game"],p["country"]) for p in officials)
    boxes=Counter((p["game"],p["country"]) for p in officials if p["product_type"]=="BOX")
    scopes=[]
    for g in games:
        r=by_id[g["id"]]
        hub=g.get("official_source") if safe_https(g.get("official_source")) else None
        for region in REGIONS:
            declared=region in g.get("regions",[]) or "GLOBAL" in g.get("regions",[])
            count=sample[g["canonical"],region]
            box_count=boxes[g["canonical"],region]
            scopes.append({
                "game_id":g["id"],"region":region,"region_declared":declared,
                "sample_records":count,"sealed_box_records":box_count,
                "sealed_box_status":"NOT_DECLARED" if not declared else ("BOX_SPEC_SAMPLE_PRESENT" if box_count else "BOX_SPEC_SAMPLE_MISSING"),
                "priority":"P0_DECLARED_GAP" if declared and not count else
                           "P1_DECLARED_SAMPLE" if declared else "P2_EXPLORATORY",
                "official_site_candidate":hub,
                "product_name_candidates":[{
                    "name":name,"status":"USER_SUBMITTED_UNVERIFIED",
                    "source_search":manufacturer_search(hub,name) if hub else None,
                    "alternate_source_search":manufacturer_search(hub,name,engine="bing") if hub else None
                } for name in r["product_name_candidates"]],
                "upcoming_name_candidates":r["upcoming_name_candidates"],
                "hit_name_candidates":r["hit_name_candidates"],
                "promo_name_candidates":r["promo_name_candidates"],
                "price_evidence":"NONE",
            })
    scopes.sort(key=lambda r:(r["priority"],r["game_id"],r["region"]))
    return {
        "version":1,"mode":"OFFLINE_DISCOVERY_NO_AUTO_PROMOTION",
        "games":30,"market_search_scopes":90,
        "declared_scopes":sum(x["region_declared"] for x in scopes),
        "official_product_samples":len(officials),
        "official_sealed_box_samples":sum(p["product_type"]=="BOX" for p in officials),
        "declared_sealed_box_spec_gaps":sum(x["region_declared"] and not x["sealed_box_records"] for x in scopes),
        "declared_official_sample_gaps":sum(x["priority"]=="P0_DECLARED_GAP" for x in scopes),
        "product_candidate_count":sum(len(r["product_name_candidates"]) for r in leads),
        "upcoming_candidate_count":sum(len(r["upcoming_name_candidates"]) for r in leads),
        "hit_candidate_count":sum(len(r["hit_name_candidates"]) for r in leads),
        "promo_candidate_count":sum(len(r["promo_name_candidates"]) for r in leads),
        "limitations":["NO_NETWORK_BY_DEFAULT","HTTP_200_IS_NOT_SPEC_VERIFICATION",
                       "GOOGLE_SITE_SEARCH_IS_A_LEAD_ONLY","NO_PAID_API","NOT_LIVE_STOCK_OR_SALE"],
        "scopes":scopes,
    }


def main(argv=None):
    p=argparse.ArgumentParser(description="Free offline 30-game source discovery, opt-in bounded source URL check")
    p.add_argument("--registry",type=Path,default=ROOT/"tcg_game_registry.json")
    p.add_argument("--intake",type=Path,default=ROOT/"tcg_user_research_intake_v625.json")
    p.add_argument("--base",type=Path,default=ROOT/"tcg_official_product_catalog_v599.json")
    p.add_argument("--supplement",type=Path,default=ROOT/"tcg_official_product_supplement_v630.json")
    p.add_argument("--additional",type=Path,default=ROOT/"tcg_official_product_supplement_v636.json")
    p.add_argument("--latest",type=Path,default=ROOT/"tcg_official_product_supplement_v637.json")
    p.add_argument("--newest",type=Path,default=ROOT/"tcg_official_product_supplement_v649.json")
    p.add_argument("--jp-proof",type=Path,default=ROOT/"tcg_official_product_supplement_v654.json")
    p.add_argument("--us-proof",type=Path,default=ROOT/"tcg_official_product_supplement_v657.json")
    p.add_argument("--jp-v659",type=Path,default=ROOT/"tcg_official_product_supplement_v659.json")
    p.add_argument("--summary-only",action="store_true")
    p.add_argument("--probe",action="store_true",help="Network opt-in: <=6 curated URLs, 1.2 second spacing")
    p.add_argument("--probe-limit",type=int,default=4)
    args=p.parse_args(argv)
    if not 0<=args.probe_limit<=MAX_PROBES:p.error("--probe-limit must be 0..6")
    try:
        additional=_read(args.additional) if args.additional.exists() else None
        latest=_read(args.latest) if args.latest.exists() else None
        newest=_read(args.newest) if args.newest.exists() else None
        jp_proof=_read(args.jp_proof) if args.jp_proof.exists() else None
        us_proof=_read(args.us_proof) if args.us_proof.exists() or args.us_proof.is_symlink() else None
        jp_v659=_read(args.jp_v659) if args.jp_v659.exists() or args.jp_v659.is_symlink() else None
        data=plan(_read(args.registry),_read(args.intake),_read(args.base),_read(args.supplement),additional,latest,newest,jp_proof,us_proof,jp_v659)
        if args.probe:
            from execution.official_box_coverage_audit_v623 import _trusted_url
            base=_read(args.base);supplement=_read(args.supplement)
            products=base["products"]+supplement["products"]+(additional["products"] if additional else [])+(latest["products"] if latest else [])+(newest["products"] if newest else [])+(jp_proof["products"] if jp_proof else [])+(us_proof["products"] if us_proof else [])+(jp_v659["products"] if jp_v659 else [])
            urls=list(dict.fromkeys(p["source"] for p in products
                         if _trusted_url(p.get("source"),p.get("game"))))
            checked=[]
            for i,url in enumerate(urls[:args.probe_limit]):
                if i:time.sleep(1.2)
                result=probe_one(url)
                checked.append({"url":url,**result})
                if result["status"]=="RATE_LIMIT_PAUSE":break
            data["http_probes"]={"checked_at":datetime.now(timezone.utc).isoformat(),
                "checked":len(checked),"results":checked,
                "note":"HTTP status only, no manufacturer specification verified"}
        if args.summary_only:data.pop("scopes")
        print(json.dumps(data,ensure_ascii=False,indent=2))
        return 0
    except (OSError,ValueError,TypeError,KeyError,json.JSONDecodeError):
        print(json.dumps({"status":"HOLD","reason":"INVALID_OR_INCOMPLETE_SOURCE_INPUT"}))
        return 2


if __name__=="__main__":
    raise SystemExit(main())

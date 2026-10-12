#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V643 — opt-in one-request free Scryfall MTG SET index, not BOX/prices.

Offline by default. Single fixed HTTPS /sets endpoint, no card-by-card crawling.
24h cache, conditional GET, capped response, rejects redirects/429 and preserves
last known good data. Complies with Scryfall API request-header guidance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta, date
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from tcg_tcgdex_sets_v640 import NoRedirect

URL = "https://api.scryfall.com/sets"
CACHE_FILE = "scryfall_mtg_sets.json"
CACHE_DIR = Path.home() / ".tcg_grader" / "scryfall_sets"
MAX_RESPONSE = 3_000_000
TTL = timedelta(hours=24)


def normalize(payload):
    if not isinstance(payload,dict) or payload.get("object")!="list" or payload.get("has_more") is not False:
        raise ValueError("PARTIAL_OR_UNEXPECTED_SCRYFALL_INDEX")
    rows=payload.get("data")
    if not isinstance(rows,list) or len(rows)>5000:
        raise ValueError("INVALID_SCRYFALL_SET_LIST")
    seen,cleaned=set(),[]
    for item in rows:
        if not isinstance(item,dict):
            raise ValueError("INVALID_SET_ITEM")
        code,name,count=item.get("code"),item.get("name"),item.get("card_count")
        if not isinstance(code,str) or not re.fullmatch("[A-Za-z0-9]{2,8}",code):
            raise ValueError("INVALID_SET_CODE")
        if not isinstance(name,str) or not name.strip() or len(name)>200:
            raise ValueError("INVALID_SET_NAME")
        if type(count) is not int or not 0<=count<=10000:
            raise ValueError("INVALID_SET_COUNT")
        if code in seen:
            raise ValueError("DUPLICATE_SET_CODE")
        seen.add(code)
        released=item.get("released_at")
        if released is not None:
            if not isinstance(released,str) or date.fromisoformat(released).isoformat()!=released:
                raise ValueError("INVALID_DATE")
        kind=item.get("set_type")
        if not isinstance(kind,str) or not 1<=len(kind)<=55:
            raise ValueError("INVALID_SET_TYPE")
        cleaned.append({"code":code,"name":name,"card_count":count,
                        "set_type":kind,"released_at":released,
                        "digital":item.get("digital") is True})
    return sorted(cleaned,key=lambda row:row["code"])


def path_for(root):
    return Path(root)/CACHE_FILE


def read_cache(root=CACHE_DIR):
    path=path_for(root)
    if not path.is_file() or path.is_symlink() or path.stat().st_size>MAX_RESPONSE:
        return None
    try:
        doc=json.loads(path.read_text(encoding="utf-8"))
        if (doc.get("schema_version")!=1 or doc.get("dataset_type")!="COMMUNITY_MTG_SET_INDEX"
            or doc.get("source_url")!=URL or not isinstance(doc.get("sets"),list)):
            return None
        stamp=datetime.fromisoformat(doc["fetched_at"])
        if stamp.tzinfo is None:
            return None
        cleaned=normalize({"object":"list","has_more":False,"data":[
            {"code":r["code"],"name":r["name"],"card_count":r["card_count"],
             "set_type":r["set_type"],"released_at":r["released_at"],"digital":r["digital"]}
            for r in doc["sets"]]})
        return doc if cleaned==doc["sets"] else None
    except (ValueError, KeyError, TypeError, OSError):
        return None


def atomic_save(root, doc):
    dest=path_for(root)
    if dest.parent.is_symlink() or dest.is_symlink():
        raise ValueError("SYMLINK_CACHE_BLOCKED")
    dest.parent.mkdir(parents=True,exist_ok=True)
    temp=None
    try:
        with tempfile.NamedTemporaryFile("w",encoding="utf-8",delete=False,
                                         dir=dest.parent,prefix=".scr_",suffix=".tmp") as fp:
            temp=Path(fp.name)
            json.dump(doc,fp,ensure_ascii=False,indent=2)
            fp.write("\n")
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(temp,dest)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def sync(root=CACHE_DIR,*,opener=None,now=None):
    clock=now or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        raise ValueError("NAIVE_CLOCK")
    old=read_cache(root)
    if old:
        stamp=datetime.fromisoformat(old["fetched_at"])
        if stamp<=clock<stamp+TTL:
            return {"status":"FRESH_CACHE","sets":len(old["sets"]),"network_calls":0}
    headers={"User-Agent":"TCG-Grader-Source-Research/1.0 (manual MTG set index)",
             "Accept":"application/json;q=0.9,*/*;q=0.8"}
    if old:
        if old.get("etag"):headers["If-None-Match"]=old["etag"]
        if old.get("last_modified"):headers["If-Modified-Since"]=old["last_modified"]
    req=Request(URL,headers=headers,method="GET")
    conn=opener or build_opener(NoRedirect())
    try:
        with conn.open(req,timeout=8) as resp:
            if resp.geturl()!=URL:
                return {"status":"REDIRECT_REVIEW","network_calls":1,"sets":len(old["sets"]) if old else 0}
            if resp.getcode()!=200:
                return {"status":"NON_200_UNVERIFIED","network_calls":1,"sets":len(old["sets"]) if old else 0}
            body=resp.read(MAX_RESPONSE+1)
            if len(body)>MAX_RESPONSE:
                raise ValueError("OVERSIZED_RESPONSE")
            cleaned=normalize(json.loads(body.decode("utf-8")))
            doc={"schema_version":1,"dataset_type":"COMMUNITY_MTG_SET_INDEX",
                 "source_url":URL,"fetched_at":clock.isoformat(),"sets":cleaned,
                 "restriction":"NOT_MANUFACTURER_BOX_OR_SEALED_SKU_OR_LIVE_PRICE"}
            if resp.headers.get("ETag"):doc["etag"]=str(resp.headers["ETag"])[:180]
            if resp.headers.get("Last-Modified"):doc["last_modified"]=str(resp.headers["Last-Modified"])[:120]
            atomic_save(root,doc)
            return {"status":"UPDATED_COMMUNITY_SETS","sets":len(cleaned),"network_calls":1}
    except HTTPError as ex:
        if ex.code==304 and old:
            old["fetched_at"]=clock.isoformat()
            atomic_save(root,old)
            return {"status":"NOT_MODIFIED","sets":len(old["sets"]),"network_calls":1}
        return {"status":("RATE_LIMIT_STOP" if ex.code==429 else
                          "ACCESS_RESTRICTED" if ex.code in (401,403) else "ERROR_LAST_GOOD"),
                "sets":len(old["sets"]) if old else 0,"network_calls":1,
                "using_stale":bool(old)}
    except (URLError,OSError,ValueError,TimeoutError,UnicodeError):
        return {"status":"ERROR_LAST_GOOD","network_calls":1,
                "sets":len(old["sets"]) if old else 0,"using_stale":bool(old)}


def main(argv=None):
    ap=argparse.ArgumentParser(description="Scryfall MTG SET index: offline unless --sync")
    ap.add_argument("--sync",action="store_true",help="Explicit single free HTTPS request")
    ap.add_argument("--cache-dir",type=Path,default=CACHE_DIR)
    args=ap.parse_args(argv)
    if args.sync:result=sync(args.cache_dir)
    else:
        cache=read_cache(args.cache_dir)
        result={"status":"OFFLINE_CACHE" if cache else "NO_CACHE_OFFLINE",
                "sets":len(cache["sets"]) if cache else 0,"network_calls":0}
    print(json.dumps({"game":"Magic: The Gathering","source":"Scryfall",
                      "report":result,"free_public_endpoint":True,
                      "warning":"COMMUNITY_SET_INDEX_NOT_SEALED_BOX_OR_MARKET_PRICE"},
                     ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V651: opt-in, one-request-per-48h Yu-Gi-Oh! SET catalog from free YGOPRODeck v7.

Local-first: --sync alone permits one HTTPS GET; no image scraping, no prices,
no card-by-card polling, no paid API, no source overwrite on bad HTTP or JSON.
Set card-count is NOT sealed booster-box packs, per-pack count, or HIT rate.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from tcg_tcgdex_sets_v640 import NoRedirect

ENDPOINT="https://db.ygoprodeck.com/api/v7/cardsets.php"
DEFAULT_DIR=Path.home()/".tcg_grader"/"ygoprodeck_sets"
CACHE_NAME="ygoprodeck_v7_sets.json"
MAX_BYTES=3_000_000
MAX_ROWS=5000
TTL=timedelta(hours=48)


def clean_sets(rows):
    if not isinstance(rows,list) or not 0<len(rows)<=MAX_ROWS:
        raise ValueError("INVALID_CARDSETS_RESPONSE")
    seen=set()
    output=[]
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError("INVALID_SET_ITEM")
        code,name,count=row.get("set_code"),row.get("set_name"),row.get("num_of_cards")
        if not isinstance(code,str) or not re.fullmatch(r"[A-Za-z0-9_-]{2,24}",code):
            raise ValueError("INVALID_SET_CODE")
        if not isinstance(name,str) or not 1<=len(name.strip())<=200:
            raise ValueError("INVALID_SET_NAME")
        if type(count) is not int or not 0<=count<=10000:
            raise ValueError("INVALID_SET_CARD_COUNT")
        if code.casefold() in seen:
            raise ValueError("DUPLICATE_SET_CODE")
        seen.add(code.casefold())
        date_text=row.get("tcg_date")
        if date_text not in (None,""):
            if not isinstance(date_text,str) or date.fromisoformat(date_text).isoformat()!=date_text:
                raise ValueError("INVALID_TCG_DATE")
        output.append({"set_code":code,"set_name":name.strip(),
                       "card_count_in_set":count,"tcg_date":date_text or None})
    return sorted(output,key=lambda r:r["set_code"])


def cache_path(folder):
    return Path(folder)/CACHE_NAME


def read_cached(folder=DEFAULT_DIR):
    loc=cache_path(folder)
    if not loc.is_file() or loc.is_symlink() or loc.stat().st_size>MAX_BYTES:
        return None
    try:
        doc=json.loads(loc.read_text(encoding="utf-8"))
        if (doc.get("schema_version")!=1 or doc.get("dataset_type")!="COMMUNITY_YGO_TCG_SET_INDEX" or
            doc.get("source_url")!=ENDPOINT or not isinstance(doc.get("rows"),list)):
            return None
        timestamp=datetime.fromisoformat(doc["fetched_at"])
        if timestamp.tzinfo is None:
            return None
        normalized=clean_sets([{"set_code":p["set_code"],"set_name":p["set_name"],
                                "num_of_cards":p["card_count_in_set"],"tcg_date":p["tcg_date"]}
                               for p in doc["rows"]])
        return doc if doc["rows"]==normalized else None
    except (ValueError,KeyError,TypeError,OSError,OverflowError):
        return None


def write_atomic(folder,doc):
    loc=cache_path(folder)
    if loc.is_symlink() or loc.parent.is_symlink():
        raise ValueError("SYMLINK_CACHE_PATH")
    loc.parent.mkdir(parents=True,exist_ok=True)
    tmp=None
    try:
        with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=loc.parent,
                                         prefix=".ygo_",suffix=".tmp",delete=False) as stream:
            tmp=Path(stream.name)
            json.dump(doc,stream,ensure_ascii=False,indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp,loc)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def sync(folder=DEFAULT_DIR,*,clock=None,opener=None):
    now=clock or datetime.now(timezone.utc)
    if not isinstance(now,datetime) or now.tzinfo is None:
        raise ValueError("INVALID_TIMEZONE")
    old=read_cached(folder)
    if old:
        stamp=datetime.fromisoformat(old["fetched_at"])
        if stamp<=now<stamp+TTL:
            return {"status":"FRESH_CACHE","sets":len(old["rows"]),"network_calls":0}
    headers={"User-Agent":"TCG-Grader-SetIndex/1.0 (opt-in, cached, non-bulk)",
             "Accept":"application/json"}
    if old:
        if old.get("etag"):headers["If-None-Match"]=old["etag"]
        if old.get("last_modified"):headers["If-Modified-Since"]=old["last_modified"]
    request=Request(ENDPOINT,headers=headers,method="GET")
    client=opener or build_opener(NoRedirect())
    try:
        with client.open(request,timeout=8) as response:
            if response.geturl()!=ENDPOINT:
                return {"status":"REDIRECT_REVIEW","sets":len(old["rows"]) if old else 0,
                        "network_calls":1,"using_stale":bool(old)}
            if response.getcode()!=200:
                return {"status":"NON_200_REVIEW","sets":len(old["rows"]) if old else 0,
                        "network_calls":1,"using_stale":bool(old)}
            body=response.read(MAX_BYTES+1)
            if len(body)>MAX_BYTES:raise ValueError("OVERSIZED_SET_INDEX")
            records=clean_sets(json.loads(body.decode("utf-8")))
            doc={"schema_version":1,"dataset_type":"COMMUNITY_YGO_TCG_SET_INDEX",
                 "source_url":ENDPOINT,"fetched_at":now.isoformat(),"rows":records,
                 "notes":"Set catalog only; not official sealed SKU, market price, MSRP or HIT odds"}
            if response.headers.get("ETag"):doc["etag"]=str(response.headers["ETag"])[:160]
            if response.headers.get("Last-Modified"):
                doc["last_modified"]=str(response.headers["Last-Modified"])[:100]
            write_atomic(folder,doc)
            return {"status":"UPDATED_COMMUNITY_SET_INDEX","sets":len(records),"network_calls":1}
    except HTTPError as error:
        if error.code==304 and old:
            old["fetched_at"]=now.isoformat()
            write_atomic(folder,old)
            return {"status":"NOT_MODIFIED","sets":len(old["rows"]),"network_calls":1}
        code=("RATE_LIMIT_STOP" if error.code==429 else
              "ACCESS_RESTRICTED" if error.code in (401,403) else "ERROR_LAST_GOOD")
        return {"status":code,"sets":len(old["rows"]) if old else 0,
                "network_calls":1,"using_stale":bool(old)}
    except (URLError,TimeoutError,OSError,ValueError,UnicodeError,OverflowError):
        return {"status":"ERROR_LAST_GOOD","sets":len(old["rows"]) if old else 0,
                "network_calls":1,"using_stale":bool(old)}


def main(argv=None):
    ap=argparse.ArgumentParser(description="Free YGOPRODeck v7 set index; OFFLINE by default")
    ap.add_argument("--sync",action="store_true",help="Explicitly allow 1 HTTPS GET if 48h cache expired")
    ap.add_argument("--cache-dir",type=Path,default=DEFAULT_DIR)
    args=ap.parse_args(argv)
    if args.sync:result=sync(args.cache_dir)
    else:
        cached=read_cached(args.cache_dir)
        result={"status":"OFFLINE_CACHE" if cached else "NO_CACHE_OFFLINE",
                "sets":len(cached["rows"]) if cached else 0,"network_calls":0}
    print(json.dumps({"game":"Yu-Gi-Oh!","data_source":"YGOPRODeck v7",
                      "free_public_set_index":True,
                      "image_downloads":0,"market_price_imports":0,"result":result,
                      "warning":"Set count is not number of sealed BOX packs/cards; no JP/KR edition claim"},
                     ensure_ascii=False,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())

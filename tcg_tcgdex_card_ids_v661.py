#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V661 opt-in Pokémon TCGdex SET card IDs: community lookup, never official SKU."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone,timedelta
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.error import HTTPError,URLError
from urllib.request import Request,build_opener
from tcg_tcgdex_sets_v640 import NoRedirect,safe_lang,API_BASE

CACHE=Path.home()/".tcg_grader"/"tcgdex_cards"
TTL=timedelta(hours=24)
MAX_BYTES=2_000_000
MAX_CARDS=1500

def safe_set(set_id):
    if not isinstance(set_id,str) or not re.fullmatch(r"[A-Za-z0-9_-]{2,40}",set_id):
        raise ValueError("UNSAFE_SET_ID")
    return set_id

def endpoint(lang,set_id):
    return API_BASE+safe_lang(lang)+"/sets/"+safe_set(set_id)

def normalize(data,set_id):
    if not isinstance(data,dict) or data.get("id")!=safe_set(set_id):
        raise ValueError("SET_ID_MISMATCH")
    name=data.get("name")
    if not isinstance(name,str) or not 1<=len(name.strip())<=180:
        raise ValueError("INVALID_SET_NAME")
    cards=data.get("cards")
    if not isinstance(cards,list) or not 1<=len(cards)<=MAX_CARDS:
        raise ValueError("INVALID_CARD_SET")
    seen=set()
    rows=[]
    for card in cards:
        if not isinstance(card,dict):raise ValueError("INVALID_CARD_OBJECT")
        ident,local,card_name=card.get("id"),card.get("localId"),card.get("name")
        if (not isinstance(ident,str) or not re.fullmatch(r"[A-Za-z0-9_-]{2,80}",ident)
            or not ident.startswith(set_id+"-") or
            not isinstance(local,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,35}",local)
            or not isinstance(card_name,str) or not 1<=len(card_name.strip())<=150 or
            ident.casefold() in seen):
            raise ValueError("UNSAFE_OR_DUPLICATE_CARD_ID")
        seen.add(ident.casefold())
        rows.append({"id":ident,"local_id":local,"name":card_name.strip()})
    return sorted(rows,key=lambda x:x["id"])

def cache_file(root,lang,set_id):
    return Path(root)/(safe_lang(lang)+"_"+safe_set(set_id)+".json")

def cached(root,lang,set_id):
    path=cache_file(root,lang,set_id)
    if not path.is_file() or path.is_symlink() or path.stat().st_size>MAX_BYTES:
        return None
    try:
        doc=json.loads(path.read_text(encoding="utf-8"))
        if (doc.get("schema_version")!=1 or doc.get("type")!="COMMUNITY_POKEMON_SET_CARD_IDS" or
            doc.get("lang")!=lang or doc.get("set_id")!=set_id or
            doc.get("source")!=endpoint(lang,set_id)):return None
        rows=normalize({"id":set_id,"name":doc["set_name"],
                        "cards":[{"id":c["id"],"localId":c["local_id"],"name":c["name"]} for c in doc["cards"]]},set_id)
        if doc["cards"]!=rows:return None
        t=datetime.fromisoformat(doc["fetched_at"])
        return doc if t.tzinfo is not None else None
    except (KeyError,TypeError,ValueError,UnicodeError,OSError):
        return None

def store(root,lang,set_id,doc):
    path=cache_file(root,lang,set_id)
    if path.is_symlink() or path.parent.is_symlink():raise ValueError("SYMLINK_CACHE")
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=None
    try:
        with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=path.parent,
                                         prefix=".cards_",suffix=".tmp",delete=False) as f:
            temp=Path(f.name)
            json.dump(doc,f,ensure_ascii=False,indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if temp is not None:temp.unlink(missing_ok=True)

def sync_one(lang,set_id,root=CACHE,*,opener=None,clock=None):
    url=endpoint(lang,set_id)
    now=clock or datetime.now(timezone.utc)
    if not isinstance(now,datetime) or now.tzinfo is None:raise ValueError("BAD_TIME")
    old=cached(root,lang,set_id)
    if old:
        timestamp=datetime.fromisoformat(old["fetched_at"])
        if timestamp<=now<timestamp+TTL:
            return {"status":"FRESH_CACHE","cards":len(old["cards"]),"network_calls":0}
    headers={"Accept":"application/json",
             "User-Agent":"TCG-Grader-Free/1.0 (manual-opt-in, one set, community IDs)"}
    if old and old.get("etag"):headers["If-None-Match"]=old["etag"]
    req=Request(url,headers=headers,method="GET")
    client=opener or build_opener(NoRedirect())
    try:
        with client.open(req,timeout=8) as r:
            if r.geturl()!=url:return {"status":"REDIRECT_REVIEW","network_calls":1,"using_stale":bool(old)}
            if r.getcode()!=200:return {"status":"HTTP_REVIEW","network_calls":1,"using_stale":bool(old)}
            raw=r.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES:raise ValueError("OVERSIZED")
            data=json.loads(raw.decode("utf-8"))
            cards=normalize(data,set_id)
            doc={"schema_version":1,"type":"COMMUNITY_POKEMON_SET_CARD_IDS",
                 "lang":lang,"set_id":set_id,"set_name":data["name"],"source":url,
                 "fetched_at":now.isoformat(),"cards":cards,
                 "restriction":"NOT MANUFACTURER VERIFIED, NOT PRICE/BOX/HIT"}
            if r.headers.get("ETag"):doc["etag"]=str(r.headers["ETag"])[:150]
            store(root,lang,set_id,doc)
            return {"status":"UPDATED_COMMUNITY_CARD_IDS","cards":len(cards),"network_calls":1}
    except HTTPError as e:
        if e.code==304 and old:
            old["fetched_at"]=now.isoformat()
            store(root,lang,set_id,old)
            return {"status":"NOT_MODIFIED","cards":len(old["cards"]),"network_calls":1}
        return {"status":"RATE_LIMIT_STOP" if e.code==429 else
                "ACCESS_RESTRICTED" if e.code in (401,403) else "ERROR_LAST_GOOD",
                "network_calls":1,"using_stale":bool(old),
                "cards":len(old["cards"]) if old else 0}
    except (URLError,TimeoutError,OSError,ValueError,TypeError,UnicodeError):
        return {"status":"ERROR_LAST_GOOD","network_calls":1,"using_stale":bool(old),
                "cards":len(old["cards"]) if old else 0}

def main(argv=None):
    p=argparse.ArgumentParser(description="One opt-in TCGdex set card-ID fetch; offline default")
    p.add_argument("--lang",choices=("en","ja"),required=True)
    p.add_argument("--set-id",required=True)
    p.add_argument("--sync",action="store_true")
    p.add_argument("--cache-dir",type=Path,default=CACHE)
    a=p.parse_args(argv)
    try:
        path=cache_file(a.cache_dir,a.lang,a.set_id)
        if a.sync:result=sync_one(a.lang,a.set_id,a.cache_dir)
        else:
            doc=cached(a.cache_dir,a.lang,a.set_id)
            result={"status":"OFFLINE_CACHE" if doc else "NO_CACHE",
                    "cards":len(doc["cards"]) if doc else 0,"network_calls":0}
        print(json.dumps({"game":"Pokémon","source":"TCGdex community",
            "set_id":a.set_id,"lang":a.lang,"no_paid_dependency":True,
            "result":result,"warning":"Community IDs only; not official BOX, HIT odds, price or graded value"},
            ensure_ascii=False,indent=2))
        return 0
    except (ValueError,OSError,UnicodeError) as e:
        p.error(str(e))
if __name__=="__main__":raise SystemExit(main())

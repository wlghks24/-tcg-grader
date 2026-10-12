#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V644: 30-game event/promo/gift/movie/collaboration discovery and source-ledger.

Standard library, offline by default. Search links only, NO scraping, external
API key, automatic purchases/entries, prizes guarantee, or paid dependency.
Exact campaign identity is conservative; broad keyword overlap makes RELATED
suggestions, not automatic merges.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from execution.official_box_coverage_audit_v623 import _trusted_url
from tcg_multi_source_queue_v639 import load_local, search_url

ROOT = Path(__file__).resolve().parent
REGIONS = ("KR", "JP", "US")
CATEGORIES = ("PROMO", "EVENT", "TOURNAMENT", "COLLAB", "MOVIE",
              "GIVEAWAY", "GIFT", "LOTTERY", "POPUP", "FESTIVAL", "PRERELEASE")
TERMS = {
 "KR": {"PROMO":("프로모 카드","한정 배포"),"EVENT":("이벤트","행사"),
        "TOURNAMENT":("대회","참가상"),"COLLAB":("콜라보","제휴"),
        "MOVIE":("영화","극장판"),"GIVEAWAY":("경품","증정"),
        "GIFT":("사은품","특전"),"LOTTERY":("추첨","응모"),
        "POPUP":("팝업스토어","오프라인 행사"),"FESTIVAL":("페스티벌","박람회"),
        "PRERELEASE":("프리릴리즈","선행체험")},
 "JP": {"PROMO":("プロモカード","配布"),"EVENT":("イベント","開催"),
        "TOURNAMENT":("大会","参加賞"),"COLLAB":("コラボ","タイアップ"),
        "MOVIE":("映画","劇場版"),"GIVEAWAY":("プレゼント","景品"),
        "GIFT":("購入特典","配布"),"LOTTERY":("抽選","応募"),
        "POPUP":("ポップアップ","期間限定"),"FESTIVAL":("フェス","展示会"),
        "PRERELEASE":("プレリリース","先行体験")},
 "US": {"PROMO":("promo card","exclusive"),"EVENT":("event","in-store"),
        "TOURNAMENT":("tournament","participation prize"),"COLLAB":("collaboration","crossover"),
        "MOVIE":("movie","film promo"),"GIVEAWAY":("giveaway","sweepstakes"),
        "GIFT":("gift","purchase bonus"),"LOTTERY":("lottery","raffle"),
        "POPUP":("pop-up","store event"),"FESTIVAL":("festival","convention"),
        "PRERELEASE":("prerelease","pre-release")},
}
TRACKING = {"utm_source","utm_medium","utm_campaign","utm_content","utm_term",
            "gclid","fbclid","igshid","mc_cid","mc_eid","ref_src","si","yclid"}
SOURCE_TYPES = {"manufacturer", "organizer", "store", "news", "instagram", "youtube", "x", "community"}
DISCOVERY = {"official", "google", "bing", "instagram", "youtube", "x", "manual", "other"}
REQUIRED = {"game_id","region","category","title","start_date","end_date",
            "location","keyword","source_url","source_type","observed_at"}
MAX_CSV_BYTES = 1_800_000
MAX_ROWS = 4000
MAX_TEXT = 230


def norm(value):
    if not isinstance(value, str) or len(value)>MAX_TEXT:
        raise ValueError("INVALID_TEXT")
    s = unicodedata.normalize("NFKC",value).casefold()
    s = "".join(ch for ch in s if ch.isalnum())
    if not s: raise ValueError("EMPTY_NORMALIZED_TEXT")
    return s


def short(value, *, allow_empty=True):
    if (not isinstance(value,str) or len(value)>MAX_TEXT or
       any(ord(ch)<32 for ch in value)):
        raise ValueError("INVALID_TEXT")
    out=" ".join(value.split())
    if not out and not allow_empty: raise ValueError("EMPTY_TEXT")
    return out


def date_value(value):
    if not value: return ""
    if not isinstance(value,str) or len(value)!=10:raise ValueError("INVALID_ISO_DATE")
    try: return date.fromisoformat(value).isoformat()
    except ValueError as exc: raise ValueError("INVALID_ISO_DATE") from exc


def safe_url(value):
    if not isinstance(value,str) or not 1<=len(value)<=900:return None
    try:
        u=urlsplit(value)
        if (u.scheme!="https" or not u.hostname or u.username or u.password or
                u.port not in (None,443)): return None
        host=u.hostname.lower().strip(".")
        if host=="localhost" or host.endswith((".local",".localhost",".test",".invalid")):
            return None
        try:ipaddress.ip_address(host);return None
        except ValueError:pass
        if "." not in host:return None
        return u
    except ValueError:return None


def canonical_url(value):
    u=safe_url(value)
    if u is None:raise ValueError("UNSAFE_URL")
    # Only analytics query params are discarded. Semantic IDs, article codes,
    # locale and search params remain, avoiding false merges.
    args=[(k,v) for k,v in parse_qsl(u.query,keep_blank_values=True)
          if k.casefold() not in TRACKING and not k.casefold().startswith("utm_")]
    path=re.sub("/+$","",u.path) or "/"
    return urlunsplit(("https",u.hostname.lower(),path,urlencode(sorted(args)), ""))


def reg_games():
    obj=load_local("tcg_game_registry.json")
    rows=obj.get("games")
    if (obj.get("schema_version")!=1 or not isinstance(rows,list) or len(rows)!=30 or
       len({g["id"] for g in rows})!=30):
        raise ValueError("INVALID_30_GAME_REGISTRY")
    return rows


def research_plan(*, game="ALL", region="ALL", category="ALL", declared_only=False):
    games=reg_games()
    if game!="ALL" and game not in {g["id"] for g in games}:
        raise ValueError("INVALID_GAME")
    if region not in ("ALL",*REGIONS) or category not in ("ALL",*CATEGORIES):
        raise ValueError("INVALID_FILTER")
    tasks=[]
    for g in games:
        if game!="ALL" and g["id"]!=game:continue
        for market in REGIONS:
            if region!="ALL" and region!=market:continue
            declared=market in g["regions"] or "GLOBAL" in g["regions"]
            if declared_only and not declared:continue
            official=safe_url(g.get("official_source"))
            if not official:raise ValueError("UNSAFE_MANUFACTURER_SITE")
            alias=g["label_ko"] if market=="KR" else g["canonical"]
            for kind in CATEGORIES:
                if category!="ALL" and category!=kind:continue
                words=TERMS[market][kind]
                q='"'+alias.replace('"',"")+'" ("'+words[0]+'" OR "'+words[1]+'")'
                s='site:'+official.hostname+' '+q
                tasks.append({
                    "game_id":g["id"],"game":g["canonical"],"region":market,
                    "category":kind,"region_declared":declared,
                    "keywords":list(words),
                    "verification_state":"SEARCH_LINK_ONLY_NOT_VERIFIED",
                    "links":{
                        "official_google":search_url("google",s),
                        "official_bing":search_url("bing",s),
                        "general_google":search_url("google",q),
                        "instagram_google":search_url("google",'site:instagram.com '+q),
                        "youtube_google":search_url("google",'site:youtube.com '+q),
                        "x_latest":search_url("x",q)},
                })
    return {"schema_version":1,"games_registered":30,"market_scopes":90,
            "search_tasks":len(tasks),"declared_tasks":sum(t["region_declared"] for t in tasks),
            "network_calls":0,"no_paid_dependencies":True,"tasks":tasks}


def load_rows_csv(text,*,file_name="input.csv"):
    if not isinstance(text,str) or len(text.encode("utf-8"))>MAX_CSV_BYTES:
        raise ValueError("OVERSIZED_CSV")
    reader=csv.DictReader(text.lstrip("\ufeff").splitlines())
    if not reader.fieldnames or not REQUIRED.issubset(reader.fieldnames):
        raise ValueError("MISSING_REQUIRED_COLUMNS")
    if len(set(reader.fieldnames))!=len(reader.fieldnames):
        raise ValueError("DUPLICATE_CSV_COLUMNS")
    records=[]
    for n,row in enumerate(reader,start=2):
        if n>MAX_ROWS+1:raise ValueError("TOO_MANY_EVENT_ROWS")
        if not row or None in row or any(v is None for v in row.values()):
            raise ValueError("INVALID_CSV_ROW_"+str(n))
        records.append({**row,"_input_file":file_name,"_input_row":n})
    return records


def clean_record(raw, games, *,today):
    gid=short(raw.get("game_id",""),allow_empty=False)
    g=games.get(gid)
    if not g:raise ValueError("UNKNOWN_GAME")
    market=short(raw.get("region",""),allow_empty=False)
    kind=short(raw.get("category",""),allow_empty=False).upper()
    if market not in REGIONS or kind not in CATEGORIES:
        raise ValueError("INVALID_REGION_OR_CATEGORY")
    title=short(raw.get("title",""),allow_empty=False)
    start=date_value(short(raw.get("start_date","")))
    end=date_value(short(raw.get("end_date","")))
    if end and not start:raise ValueError("END_WITHOUT_START")
    if end and end<start:raise ValueError("REVERSED_EVENT_DATES")
    observed=date_value(short(raw.get("observed_at",""),allow_empty=False))
    if observed>today.isoformat():raise ValueError("FUTURE_SOURCE_OBSERVATION")
    loc=short(raw.get("location",""))
    reward=short(raw.get("reward",""))
    eligibility=short(raw.get("eligibility",""))
    keyword=short(raw.get("keyword",""))
    campaign_id=short(raw.get("campaign_id",""))
    source=raw.get("source_url","")
    if not isinstance(source,str) or not source or any(ord(ch)<32 for ch in source):
        raise ValueError("INVALID_SOURCE_URL")
    canonical=canonical_url(source)
    channel=short(raw.get("discovery_channel","") or "manual").lower()
    if channel not in DISCOVERY:raise ValueError("INVALID_DISCOVERY_CHANNEL")
    src_type=short(raw.get("source_type",""),allow_empty=False).lower()
    if src_type not in SOURCE_TYPES:raise ValueError("UNKNOWN_SOURCE_TYPE")
    # Matching an allowed manufacturer HOST is not proof that the page says the claim.
    manufacturer_host_ok=_trusted_url(source,g["canonical"]) if src_type=="manufacturer" else False
    if src_type=="manufacturer" and not manufacturer_host_ok:
        # Preserve claimed manufacturer source as untrusted staging, never certify it.
        trust="CLAIMED_MANUFACTURER_HOST_NOT_ALLOWLISTED"
    elif manufacturer_host_ok:trust="MANUFACTURER_HOST_ONLY_CONTENT_UNREVIEWED"
    else:trust="SECONDARY_SOURCE_NOT_OFFICIAL_PROOF"
    return {
       "game_id":gid,"game":g["canonical"],"region":market,"category":kind,
       "title":title,"start_date":start,"end_date":end,
       "location":loc,"reward":reward,"eligibility":eligibility,
       "keyword":keyword,"campaign_id":campaign_id,
       "source_url":source,"canonical_url":canonical,"source_type":src_type,
       "discovery_channel":channel,
       "observed_at":observed,"source_trust":trust,
       "input_file":str(raw.get("_input_file","manual.csv"))[:120],
       "input_row":raw.get("_input_row",0)
    }


def group_records(raw_rows, *,today=None):
    clock=today or date.today()
    if not isinstance(clock,date):raise ValueError("INVALID_TODAY")
    games={g["id"]:g for g in reg_games()}
    groups,source_index,issues={}, {}, []
    for index, raw in enumerate(raw_rows,1):
        try:r=clean_record(raw,games,today=clock)
        except (ValueError,KeyError,TypeError) as err:
            issues.append({"row":index,"reason":str(err)})
            continue
        title=norm(r["title"])
        # Same phrase on two posters is not same event if day or venue differs.
        # Without dates, only identical canonical URL can be safely grouped.
        if r["start_date"]:
            identity=(r["game_id"],r["region"],r["category"],title,
                      r["start_date"],norm(r["location"]) if r["location"] else "")
        else:
            identity=(r["game_id"],r["region"],r["category"],title,
                      "",r["canonical_url"])
        eid=hashlib.sha256(json.dumps(identity,ensure_ascii=False).encode("utf-8")).hexdigest()[:20]
        if eid not in groups:
            groups[eid]={
                "event_id":eid,"game_id":r["game_id"],"game":r["game"],
                "region":r["region"],"category":r["category"],"title":r["title"],
                "start_date":r["start_date"] or None,"end_dates":[],
                "locations":[],"rewards":[],"eligibility":[],"campaign_ids":[],
                "keywords":[],"sources":[],"source_count":0,"primary_source_url":None,
                "validation_status":"MANUAL_CONTENT_REVIEW_REQUIRED",
                "confirmed":False
            }
        e=groups[eid]
        for field,key in (("end_dates","end_date"),("locations","location"),
                          ("rewards","reward"),("eligibility","eligibility"),
                          ("campaign_ids","campaign_id"),("keywords","keyword")):
            val=r[key]
            if val and val not in e[field]:e[field].append(val)
        source_key=(eid,r["canonical_url"])
        if source_key in source_index:
            # Same destination discovered via Google, Bing and official news:
            # only one source URL card, with every discovery route retained.
            existing=source_index[source_key]
            existing["sightings"]+=1
            if r["discovery_channel"] not in existing["found_via"]:
                existing["found_via"].append(r["discovery_channel"])
            if r["keyword"] and r["keyword"] not in existing["keywords_found"]:
                existing["keywords_found"].append(r["keyword"])
            provenance={"file":r["input_file"],"row":r["input_row"]}
            if provenance not in existing["discovered_in"]:
                existing["discovered_in"].append(provenance)
            if r["observed_at"]>existing["last_observed_at"]:
                existing["last_observed_at"]=r["observed_at"]
            continue
        record={
            "url":r["source_url"],"canonical_url":r["canonical_url"],
            "source_type":r["source_type"],"observed_at":r["observed_at"],
            "last_observed_at":r["observed_at"],"source_trust":r["source_trust"],
            "keywords_found":[r["keyword"]] if r["keyword"] else [],
            "found_via":[r["discovery_channel"]],"sightings":1,
            "discovered_in":[{"file":r["input_file"],"row":r["input_row"]}],
        }
        source_index[source_key]=record
        e["sources"].append(record)
    events=list(groups.values())
    rank={"MANUFACTURER_HOST_ONLY_CONTENT_UNREVIEWED":0,
          "SECONDARY_SOURCE_NOT_OFFICIAL_PROOF":1,
          "CLAIMED_MANUFACTURER_HOST_NOT_ALLOWLISTED":2}
    for e in events:
        e["sources"].sort(key=lambda s:(rank.get(s["source_trust"],9),s["canonical_url"]))
        e["source_count"]=len(e["sources"])
        e["primary_source_url"]=e["sources"][0]["url"] if e["sources"] else None
        if len(e["end_dates"])>1 or len(e["rewards"])>1 or len(e["campaign_ids"])>1:
            e["validation_status"]="MULTIPLE_DETAILS_REVIEW_REQUIRED"
    events.sort(key=lambda e:(e["start_date"] or "9999-12-31",e["game_id"],e["event_id"]))
    # Similar campaigns from many sources are only suggested for manual review.
    # Inverted indices avoid an unconditional O(events²) tablet/Termux scan.
    from collections import defaultdict
    from itertools import combinations
    candidate_buckets=defaultdict(list)
    for ev in events:
        candidate_buckets[("title",ev["game_id"],ev["category"],norm(ev["title"]))].append(ev)
        if ev["start_date"]:
            for keyword in ev["keywords"]:
                candidate_buckets[("keyword",ev["game_id"],ev["category"],ev["region"],
                                   ev["start_date"],norm(keyword))].append(ev)
    possible,review_pairs=[],set()
    for label,bucket in candidate_buckets.items():
        if len(bucket)<2:continue
        # Cap noisy generic keywords; missed similarities remain separate, never
        # falsely auto-combined or assigned official status.
        limited=bucket[:60]
        for x,y in combinations(limited,2):
            pair=tuple(sorted((x["event_id"],y["event_id"])))
            if pair in review_pairs:continue
            mismatch=(x["region"]!=y["region"] or x["start_date"]!=y["start_date"]
                      or x["locations"]!=y["locations"])
            if label[0]=="title" and not mismatch:continue
            reason=("SAME_TITLE_DIFFERENT_REGION_DATE_OR_LOCATION" if label[0]=="title"
                    else "SHARED_KEYWORD_SAME_DATE_REVIEW_ONLY")
            review_pairs.add(pair)
            possible.append({"event_ids":list(pair),"reason":reason})
            if len(possible)>=1000:break
        if len(possible)>=1000:break
    return {"schema_version":1,"dataset_type":"TCG_EVENT_DISCOVERY_LEDGER",
            "verified":False,"game_count":30,"input_sightings":len(raw_rows),
            "events":events,"unique_events":len(events),
            "source_sightings_retained":sum(e["source_count"] for e in events),
            "total_discoveries":sum(src["sightings"] for ev in events for src in ev["sources"]),
            "rejected":issues,"possible_duplicate_review":possible,
            "policy":"NO_AUTO_PROMOTION_NO_PRIZE_GUARANTEE_NO_AUTO_ENTRY_NO_PAID_API"}


def main(argv=None):
    ap=argparse.ArgumentParser(description="Free 30-TCG event/promo multi-source search and duplicate ledger")
    ap.add_argument("--plan",action="store_true",help="Generate offline research queries")
    ap.add_argument("--game",default="ALL")
    ap.add_argument("--region",default="ALL")
    ap.add_argument("--category",default="ALL")
    ap.add_argument("--declared-only",action="store_true")
    ap.add_argument("--input",type=Path,action="append",help="CSV input (repeat to combine sources)")
    ap.add_argument("--output",type=Path,help="New JSON ledger path; do not overwrite")
    ap.add_argument("--summary-only",action="store_true")
    args=ap.parse_args(argv)
    try:
        if args.plan or not args.input:
            result=research_plan(game=args.game,region=args.region,
                                 category=args.category,declared_only=args.declared_only)
            if args.summary_only:result.pop("tasks")
        else:
            all_rows=[]
            for path in args.input:
                if not path.is_file() or path.is_symlink() or path.stat().st_size>MAX_CSV_BYTES:
                    raise ValueError("INVALID_CSV_FILE")
                all_rows.extend(load_rows_csv(path.read_text(encoding="utf-8-sig"),
                                              file_name=path.name))
                if len(all_rows)>MAX_ROWS:raise ValueError("TOO_MANY_INPUT_ROWS")
            result=group_records(all_rows)
            if args.summary_only:
                result={k:v for k,v in result.items() if k not in
                        ("events","rejected","possible_duplicate_review")}
        body=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
        if args.output:
            import os
            import tempfile
            out=args.output
            if (out.suffix.lower()!=".json" or out.exists() or out.is_symlink() or
               out.resolve().parent==ROOT.resolve()):raise ValueError("UNSAFE_LEDGER_OUTPUT")
            out.parent.mkdir(parents=True,exist_ok=True)
            temp=None
            try:
                with tempfile.NamedTemporaryFile("w",encoding="utf-8",
                     dir=out.parent,prefix=".event_",suffix=".tmp",delete=False) as fp:
                    temp=Path(fp.name);fp.write(body);fp.flush();os.fsync(fp.fileno())
                os.replace(temp,out)
            finally:
                if temp:temp.unlink(missing_ok=True)
            print(json.dumps({"output":str(out),"events":result.get("unique_events"),
                              "network_calls":0},ensure_ascii=False))
        else:print(body,end="")
        return 0
    except (ValueError,TypeError,OSError,KeyError) as err:
        ap.error(str(err))

if __name__=="__main__":
    raise SystemExit(main())

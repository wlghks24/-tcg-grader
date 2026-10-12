#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V647 free offline RSS/Atom event-lead ingestion for 30 TCG games.

Reads downloaded XML files; no automatic RSS scraping, account, API key or
payments. Never confuses publication date with event date. Outputs V644-compatible
unverified sightings for multi-source review and deduplication.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
import io
import json
import os
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

from execution.official_box_coverage_audit_v623 import _trusted_url
from tcg_event_intelligence_v644 import (CATEGORIES, REGIONS, TERMS, canonical_url,
                                          reg_games, safe_url, short)

MAX_FEED_BYTES=1_800_000
MAX_ITEMS=1000
MAX_FEEDS=12
CSV_FIELDS=("game_id","region","category","title","start_date","end_date",
            "location","keyword","source_url","source_type","observed_at",
            "reward","eligibility","campaign_id","discovery_channel")


def _strip_ns(tag):
    return str(tag).split("}")[-1].lower()


def _get(el, name):
    for x in list(el):
        if _strip_ns(x.tag)==name and x.text:
            return x.text.strip()
    return ""


def parse_feed(blob):
    if not isinstance(blob,bytes) or len(blob)>MAX_FEED_BYTES:
        raise ValueError("FEED_TOO_LARGE")
    if b"<!DOCTYPE" in blob.upper() or b"<!ENTITY" in blob.upper():
        raise ValueError("XML_DTD_DISABLED")
    try:root=ET.fromstring(blob)
    except ET.ParseError as exc:raise ValueError("INVALID_XML") from exc
    top=_strip_ns(root.tag)
    if top not in ("rss","feed","rdf"):
        raise ValueError("NOT_RSS_OR_ATOM")
    items=[]
    for el in root.iter():
        if _strip_ns(el.tag) not in ("item","entry"):continue
        title=_get(el,"title")
        href=_get(el,"link")
        if not href:
            for x in list(el):
                if _strip_ns(x.tag)=="link" and x.attrib.get("href"):
                    href=x.attrib["href"].strip()
                    if x.attrib.get("rel","alternate")=="alternate":break
        if not title or not safe_url(href):continue
        if len(title)>230:continue
        items.append({"title":title,"source_url":href})
        if len(items)>MAX_ITEMS:raise ValueError("TOO_MANY_FEED_ITEMS")
    return items


def classify(title,region):
    if region not in REGIONS:raise ValueError("UNKNOWN_REGION")
    needle=title.casefold()
    result=[]
    for kind in CATEGORIES:
        words=TERMS[region][kind]
        hits=[word for word in words if word.casefold() in needle]
        if hits:result.append((kind,hits[0]))
    return result


def ingest(blobs,*,game_id,region,observed_at=None):
    games={g["id"]:g for g in reg_games()}
    if game_id not in games or region not in REGIONS:
        raise ValueError("UNKNOWN_GAME_OR_REGION")
    today=observed_at or date.today()
    if not isinstance(today,date):raise ValueError("INVALID_OBSERVATION_DAY")
    lines,seen,rejected=[],set(),[]
    count=0
    for data in blobs:
        entries=parse_feed(data)
        for item in entries:
            count+=1
            classes=classify(item["title"],region)
            if not classes:
                rejected.append({"title":item["title"],"reason":"NO_EVENT_KEYWORD"})
                continue
            # Multiple matching event types produce independent, unverified
            # classifications so a giveaway/movie collab is not omitted.
            for kind,keyword in classes:
                uid=(game_id,region,kind,canonical_url(item["source_url"]))
                if uid in seen:continue
                seen.add(uid)
                manufacturer=_trusted_url(item["source_url"],games[game_id]["canonical"])
                lines.append({
                  "game_id":game_id,"region":region,"category":kind,
                  "title":item["title"],"start_date":"","end_date":"",
                  "location":"","keyword":keyword,"source_url":item["source_url"],
                  "source_type":"manufacturer" if manufacturer else "news",
                  "observed_at":today.isoformat(),
                  "reward":"","eligibility":"","campaign_id":"",
                  "discovery_channel":"official" if manufacturer else "other",
                })
    return {"schema_version":1,"dataset_type":"TCG_OFFLINE_EVENT_FEED_LEADS",
            "feed_items_read":count,"sightings":lines,
            "classified_sightings":len(lines),"skipped_items":len(rejected),
            "rejections":rejected[:100],
            "source_policy":"LOCAL_RSS_FILE_NO_NETWORK_AUTO_SCRAPE",
            "warning":"ARTICLE_PUBLISHED_DATE_IS_NOT_EVENT_DATE; ALL SIGHTINGS UNVERIFIED"}


def csv_out(sightings):
    b=io.StringIO()
    writer=csv.DictWriter(b,fieldnames=CSV_FIELDS)
    writer.writeheader()
    for r in sightings:writer.writerow({k:r.get(k,"") for k in CSV_FIELDS})
    return b.getvalue()


def main(argv=None):
    ap=argparse.ArgumentParser(description="Free offline 30-TCG RSS/Atom event collector")
    ap.add_argument("--feed",type=Path,action="append",required=True,
                    help="Locally saved authorized RSS/Atom XML (repeat up to 12)")
    ap.add_argument("--game",required=True)
    ap.add_argument("--region",choices=REGIONS,required=True)
    ap.add_argument("--format",choices=("json","csv"),default="json")
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args(argv)
    try:
        if len(args.feed)>MAX_FEEDS:raise ValueError("TOO_MANY_FEEDS")
        blobs=[]
        for p in args.feed:
            if not p.is_file() or p.is_symlink() or p.stat().st_size>MAX_FEED_BYTES:
                raise ValueError("INVALID_FEED_FILE")
            blobs.append(p.read_bytes())
        result=ingest(blobs,game_id=args.game,region=args.region)
        content=(json.dumps(result,ensure_ascii=False,indent=2)+"\n" if args.format=="json"
                 else csv_out(result["sightings"]))
        target=args.output
        suffix=".json" if args.format=="json" else ".csv"
        if (target.suffix.lower()!=suffix or target.exists() or target.is_symlink() or
           target.resolve().parent==Path(__file__).resolve().parent):
            raise ValueError("UNSAFE_OUTPUT_PATH")
        target.parent.mkdir(parents=True,exist_ok=True)
        tmp=None
        try:
            with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=target.parent,
                                             prefix=".tcg_feed_",suffix=".tmp",delete=False) as f:
                tmp=Path(f.name);f.write(content);f.flush();os.fsync(f.fileno())
            os.replace(tmp,target)
        finally:
            if tmp:tmp.unlink(missing_ok=True)
        print(json.dumps({"read":result["feed_items_read"],
                          "event_sightings":result["classified_sightings"],
                          "skipped":result["skipped_items"],"network_calls":0,
                          "output":str(target)},ensure_ascii=False))
        return 0
    except (ValueError,TypeError,OSError,ET.ParseError) as err:
        ap.error(str(err))


if __name__=="__main__":
    raise SystemExit(main())

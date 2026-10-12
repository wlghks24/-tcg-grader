#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V660 free offline evidence gate: manufacturer card identity != trade price proof.

Manual market CSV may only become UNVERIFIED staging records. No HTTP requests,
no payment/account access, no price estimate, no odds/PSA inference.
"""
from __future__ import annotations
import argparse
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import io
import ipaddress
import json
from pathlib import Path
from urllib.parse import urlsplit
from execution.official_box_coverage_audit_v623 import ROOT, _load_json

DATA_NAME = "tcg_manufacturer_card_evidence_v660.json"
MAX_INPUT_BYTES = 1_000_000
MAX_ROWS = 2000
CURRENCY = {"KR":"KRW","JP":"JPY","US":"USD"}
PRICE_TYPES = {"STORE_BUY_OFFER","SALE_LISTING","COMPLETED_SALE_CLAIM"}
PRINTING = {"BASE","ALT_ART","UNKNOWN"}
GRADE_SERVICES = {"RAW","PSA","BGS","CGC","TAG","BRG"}
CSV_FIELDS = ("card_ref","market","source_type","source_url","observed_at",
              "currency","amount","condition","grade_service","grade")
# This is a tiny confirmed identity bootstrap; not a comprehensive card list.
EXPECTED = {
    "digimon-US-BT25-001-regular": ("digimon","US","BT25-001","Tokomon","C","BASE",
        "https://world.digimoncard.com/cards/?category=522036&search=true"),
    "digimon-US-BT25-020-alt": ("digimon","US","BT25-020","Marsmon","SR","ALT_ART",
        "https://world.digimoncard.com/cards/?category=522036&search=true"),
    "onepiece-JP-OP13-001": ("onepiece","JP","OP13-001","モンキー・D・ルフィ",None,"UNKNOWN",
        "https://cp.onepiece-cardgame.com/flame-flame-fruit/side-event/event2"),
}

def valid_source(value):
    if not isinstance(value,str) or len(value)>1000: return False
    try:
        u=urlsplit(value)
        host=(u.hostname or "").lower()
        if u.scheme!="https" or not host or u.username or u.password or u.fragment or u.port not in (None,443):
            return False
        if host=="localhost" or host.endswith((".localhost",".local",".invalid",".test",".internal")):
            return False
        try: ipaddress.ip_address(host); return False
        except ValueError: pass
        return "." in host
    except ValueError: return False

def official_card_records(doc):
    if (not isinstance(doc,dict) or doc.get("schema_version")!=1 or
        doc.get("level")!="MANUFACTURER_CARD_IDENTITY_SAMPLE" or
        not isinstance(doc.get("records"),list) or len(doc["records"])!=len(EXPECTED)):
        raise ValueError("INVALID_CARD_EVIDENCE_CATALOG")
    result={}
    for row in doc["records"]:
        if not isinstance(row,dict): raise ValueError("INVALID_CARD_ROW")
        rid=row.get("id"); ex=EXPECTED.get(rid)
        if not ex or rid in result: raise ValueError("DUPLICATE_OR_UNAPPROVED_CARD")
        identity=(row.get("game_id"),row.get("market"),row.get("card_number"),
                  row.get("card_name"),row.get("rarity"),row.get("printing"),row.get("source_url"))
        if (identity!=ex or row.get("evidence_type") not in
            ("MANUFACTURER_CARD_LIST","MANUFACTURER_OFFICIAL_EVENT_CARD_REFERENCE") or
            not valid_source(row.get("source_url")) or
            any(k in row for k in ("price","pull_rate","psa_grade","verified_sale","hit_probability"))):
            raise ValueError("FORGED_CARD_IDENTITY")
        result[rid]=row
    if set(result)!=set(EXPECTED): raise ValueError("MISSING_OFFICIAL_CARD_ID")
    return result

def price_value(value):
    try:
        v=Decimal(str(value).strip().replace(",",""))
        if not v.is_finite() or not Decimal("0")<v<=Decimal("1000000000") or v.as_tuple().exponent < -2:
            raise ValueError("INVALID_PRICE")
        return format(v,"f")
    except (InvalidOperation,TypeError):
        raise ValueError("INVALID_PRICE")

def stage_csv(text,doc=None,*,as_of=None):
    if not isinstance(text,str) or len(text.encode("utf-8"))>MAX_INPUT_BYTES:
        raise ValueError("OVERSIZED_CSV")
    ids=official_card_records(doc or _load_json(ROOT/DATA_NAME))
    as_of=as_of or date.today()
    if not isinstance(as_of,date): raise ValueError("INVALID_DATE")
    reader=csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    if not reader.fieldnames or set(reader.fieldnames)!=set(CSV_FIELDS):
        raise ValueError("INVALID_CSV_COLUMNS")
    accepted,rejected,seen=[],[],set()
    for index,row in enumerate(reader,start=2):
        if index>MAX_ROWS+1:raise ValueError("ROW_LIMIT_EXCEEDED")
        try:
            if None in row or any(v is None for v in row.values()): raise ValueError("MALFORMED_CSV_ROW")
            ref=row["card_ref"].strip()
            record=ids.get(ref)
            if record is None: raise ValueError("UNVERIFIED_CARD_NUMBER_OR_PRINTING")
            market=row["market"].strip().upper()
            if market!=record["market"]: raise ValueError("COUNTRY_EDITION_MISMATCH")
            src=row["source_url"].strip()
            if not valid_source(src): raise ValueError("UNSAFE_MARKET_SOURCE")
            kind=row["source_type"].strip().upper()
            if kind not in PRICE_TYPES: raise ValueError("PRICE_KIND_UNKNOWN")
            observed=date.fromisoformat(row["observed_at"].strip())
            if observed>as_of: raise ValueError("FUTURE_PRICE_DATE")
            if (as_of-observed).days>366: raise ValueError("STALE_PRICE_SOURCE")
            cur=row["currency"].strip().upper()
            if cur!=CURRENCY[market]: raise ValueError("CURRENCY_COUNTRY_MISMATCH")
            amount=price_value(row["amount"])
            condition=row["condition"].strip().upper()
            if condition not in ("NM","LP","MP","HP","DMG","UNSPECIFIED"):
                raise ValueError("CONDITION_UNKNOWN")
            service=row["grade_service"].strip().upper()
            if service not in GRADE_SERVICES: raise ValueError("GRADE_SERVICE_UNKNOWN")
            grade=row["grade"].strip()
            if service=="RAW":
                if grade: raise ValueError("RAW_WITH_GRADE")
            else:
                if condition!="UNSPECIFIED": raise ValueError("SLAB_WITH_RAW_CONDITION")
                try:
                    n=Decimal(grade)
                    if not 1<=n<=10 or n.as_tuple().exponent < -1:
                        raise ValueError("INVALID_GRADE")
                except (InvalidOperation,ValueError): raise ValueError("INVALID_GRADE")
            key=(ref,market,kind,src,observed.isoformat(),cur,amount,
                 condition,service,grade)
            if key in seen:continue
            seen.add(key)
            rid=hashlib.sha256(repr(key).encode("utf-8")).hexdigest()[:24]
            accepted.append({
                "record_id":rid,"card_ref":ref,"game_id":record["game_id"],
                "market":market,"card_number":record["card_number"],
                "printing":record["printing"],"source_type":kind,"source_url":src,
                "observed_at":observed.isoformat(),"reported_currency":cur,
                "reported_amount":amount,"condition":condition,
                "grade_service":service,"grade":grade or None,
                "evidence_status":"USER_SUPPLIED_UNVERIFIED",
                "is_completed_sale_verified":False,"is_market_price_verified":False,
                "eligible_for_public_price_index":False,
            })
        except (ValueError,TypeError,KeyError) as exc:
            rejected.append({"row":index,"reason":str(exc)})
    return {"schema_version":1,"status":"STAGING_ONLY_NOT_LIVE_PRICES",
            "accepted_count":len(accepted),"rejected_count":len(rejected),
            "verified_sale_count":0,"network_calls":0,"paid_dependencies":0,
            "accepted":accepted,"rejected":rejected,
            "note":"Observed listing/buylist/completed-sale claim cannot become real transacted price without independent verification."}

def main(argv=None):
    p=argparse.ArgumentParser(description="Offline manufacturer card identity / market evidence gate")
    p.add_argument("--identity-summary",action="store_true")
    p.add_argument("--csv",type=Path)
    a=p.parse_args(argv)
    try:
        identities=official_card_records(_load_json(ROOT/DATA_NAME))
        if a.csv is None:
            print(json.dumps({"verified_identity_samples":len(identities),
                "games":len({v["game_id"] for v in identities.values()}),
                "verified_prices":0,"network_calls":0},ensure_ascii=False))
        else:
            if not a.csv.is_file() or a.csv.is_symlink() or a.csv.stat().st_size>MAX_INPUT_BYTES:
                raise ValueError("UNSAFE_CSV_FILE")
            report=stage_csv(a.csv.read_text(encoding="utf-8-sig"))
            print(json.dumps(report,ensure_ascii=False,indent=2))
        return 0
    except (OSError,ValueError,TypeError,UnicodeError) as exc:
        print(json.dumps({"status":"HOLD","error":str(exc)},ensure_ascii=False))
        return 2

if __name__=="__main__":
    raise SystemExit(main())

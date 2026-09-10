#!/usr/bin/env python3
from __future__ import annotations
from datetime import date, datetime, timedelta

CONTENT_TYPES = frozenset({
    "release", "rerelease", "promo", "event", "movie_bonus", "festival", "card_news", "product_news"
})
OFFICIAL_FACT_TYPE = {
    "release":"official_release", "rerelease":"official_reprint", "promo":"official_promo",
    "event":"official_event", "movie_bonus":"official_movie_bonus", "festival":"official_event",
    "card_news":"official_release", "product_news":"official_release",
}
ACTIVE_POST_END_DAYS = 5

def normalize_content_type(value:str)->str:
    v=str(value or "").strip().lower().replace("-","_").replace(" ","_")
    aliases={"reprint":"rerelease","movie":"movie_bonus","moviebonus":"movie_bonus","fest":"festival","news":"card_news","card_release":"release"}
    v=aliases.get(v,v)
    if v not in CONTENT_TYPES: raise ValueError(f"UNKNOWN_CONTENT_TYPE:{v}")
    return v

def verification_fact_type(value:str)->str:
    return OFFICIAL_FACT_TYPE[normalize_content_type(value)]

def lifecycle_bucket(*,end_date:str|date|None,as_of:str|date|None=None)->str:
    if end_date is None: return "CURRENT"
    def parse(v):
        if isinstance(v,date) and not isinstance(v,datetime): return v
        return date.fromisoformat(str(v)[:10])
    end=parse(end_date); today=parse(as_of) if as_of is not None else date.today()
    return "CURRENT" if today <= end + timedelta(days=ACTIVE_POST_END_DAYS) else "ARCHIVE"

def self_test()->None:
    assert normalize_content_type("festival")=="festival"
    assert verification_fact_type("festival")=="official_event"
    assert lifecycle_bucket(end_date="2026-09-05",as_of="2026-09-10")=="CURRENT"
    assert lifecycle_bucket(end_date="2026-09-05",as_of="2026-09-11")=="ARCHIVE"
    print("Instagram card taxonomy: PASS")
if __name__=="__main__": self_test()

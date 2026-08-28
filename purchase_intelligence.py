#!/usr/bin/env python3
"""실시간 구매 신호 탐색기.

- 공개 웹 검색 RSS를 사용해 최근 입고/재입고/판매/후기/품절 신호를 짧게 구조화한다.
- 실제 재고라고 단정하지 않으며, 검색 결과는 구매 가능성 참고 신호로만 사용한다.
- API 키 없이 동작하도록 설계했으며 네트워크 차단 시 기존 구매처 데이터는 그대로 유지한다.
"""
from __future__ import annotations
import html, json, re, time, os, threading
from collections import OrderedDict
from safe_runtime import env_int, safe_urlopen, validate_public_https_url
from datetime import datetime, timezone
from urllib.parse import quote_plus
from urllib.request import Request
from urllib.error import URLError, HTTPError
from xml.etree import ElementTree as ET

UA = "TCG-Grader-Purchase-Research/46 (+local personal research app)"
MAX_ITEMS = 12
CACHE_TTL = 300
MAX_CACHE_ENTRIES = 256
_CACHE: OrderedDict[str, tuple[float, dict]] = OrderedDict()
_CACHE_LOCK = threading.RLock()

POSITIVE = ("재입고","입고","판매중","구매","구매완료","예약","예약판매","재고","restock","in stock","available","preorder")
NEGATIVE = ("품절","매진","sold out","out of stock","판매종료","마감")
REVIEW = ("후기","리뷰","방문","구매기","개봉","review","blog")


def _clean(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()[:500]


def _safe_http_url(url: str) -> bool:
    try:
        validate_public_https_url(url)
        return True
    except (TypeError, ValueError):
        return False


def _score(title: str, desc: str) -> tuple[int,str,list[str]]:
    s=(title+" "+desc).lower(); score=40; reasons=[]
    pos=[x for x in POSITIVE if x.lower() in s]
    neg=[x for x in NEGATIVE if x.lower() in s]
    rev=[x for x in REVIEW if x.lower() in s]
    if pos: score += min(35, 8*len(pos)); reasons.append("최근 구매·입고 신호")
    if rev: score += min(12, 4*len(rev)); reasons.append("후기·리뷰 신호")
    if neg: score -= min(45, 15*len(neg)); reasons.append("품절·마감 신호")
    score=max(5,min(95,score))
    label="높음" if score>=75 else "보통" if score>=50 else "낮음"
    return score,label,reasons


def search_web_signals(query: str, region: str="KR", game: str="", limit: int=MAX_ITEMS) -> dict:
    query=query.strip()[:120] if isinstance(query,str) else ""
    if not query:
        return {"ok":False,"error":"검색어가 필요합니다","items":[]}
    if region not in {"KR","JP","US"}:
        return {"ok":False,"error":"지원되지 않는 국가입니다","items":[]}
    if game not in {"","Pokemon","ONE PIECE","NARUTO"}:
        return {"ok":False,"error":"지원되지 않는 카드게임입니다","items":[]}
    try:
        limit=max(1,min(int(limit),MAX_ITEMS))
    except (TypeError,ValueError,OverflowError):
        limit=MAX_ITEMS
    key=f"{region}|{game}|{query}|{limit}"
    now=time.monotonic()
    with _CACHE_LOCK:
        for stale in [name for name,(created,_) in _CACHE.items() if now-created>=CACHE_TTL]:
            _CACHE.pop(stale,None)
        cached=_CACHE.get(key)
        if cached:
            _CACHE.move_to_end(key)
            return {**cached[1],"cached":True}
    region_terms={"KR":"한국 구매 재입고 후기", "JP":"日本 購入 再入荷 レビュー", "US":"buy restock review"}
    game_terms={"Pokemon":"포켓몬 Pokemon", "ONE PIECE":"원피스 ONE PIECE", "NARUTO":"나루토 NARUTO"}
    q=" ".join(x for x in (game_terms.get(game,game),query,region_terms.get(region,"")) if x)
    url="https://www.bing.com/search?format=rss&q="+quote_plus(q)
    req=Request(url,headers={"User-Agent":UA,"Accept":"application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.5"})
    try:
        with safe_urlopen(req,timeout=env_int('TCG_HTTP_TIMEOUT',15,5,45),allowed_hosts={'www.bing.com','bing.com'}) as r:
            raw=r.read(600_000)
        if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
            raise ValueError("XML 문서 선언 또는 엔티티 확장은 허용되지 않습니다")
        root=ET.fromstring(raw)
        rows=[]
        for item in root.findall(".//item")[:limit]:
            title=_clean(item.findtext("title") or "")
            link=(item.findtext("link") or "").strip()
            desc=_clean(item.findtext("description") or "")
            pub=_clean(item.findtext("pubDate") or "")
            if not title or not _safe_http_url(link): continue
            score,label,reasons=_score(title,desc)
            rows.append({"title":title,"url":link,"summary":desc[:240],"published":pub,"score":score,"probability":label,"signals":reasons,"source_type":"웹검색·후기"})
        result={"ok":True,"query":q,"region":region,"game":game,"checked_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),"items":rows,
                "notice":"검색·후기 문구를 기반으로 한 참고 신호입니다. 실제 재고는 판매처에서 최종 확인하세요."}
    except (URLError, HTTPError, TimeoutError, OSError, ET.ParseError, UnicodeDecodeError, ValueError) as exc:
        # v73: expected network/XML failures degrade gracefully. Programming errors
        # (NameError/AttributeError/etc.) must surface to the regression tests instead
        # of being mislabeled as an ordinary network outage.
        result={"ok":False,"query":q,"region":region,"game":game,"checked_at":datetime.now(timezone.utc).isoformat(timespec="seconds"),"items":[],
                "error":f"실시간 웹 신호 수집 실패: {type(exc).__name__}","notice":"네트워크 제한 시 저장된 구매처 목록을 계속 사용할 수 있습니다."}
    if result.get("ok"):
        with _CACHE_LOCK:
            _CACHE[key]=(time.monotonic(),result)
            _CACHE.move_to_end(key)
            while len(_CACHE)>MAX_CACHE_ENTRIES:
                _CACHE.popitem(last=False)
    return result

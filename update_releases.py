#!/usr/bin/env python3
"""Conservatively refresh official TCG release data for GitHub Pages."""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "releases.json"
HEADERS = {"User-Agent": "TCG-Grader-Release-Checker/1.0 (+GitHub Pages; official pages only)"}
ALLOWED = {
    "pokemoncard.co.kr", "www.pokemoncard.co.kr",
    "www.pokemon-card.com", "www.30th.pokemon-card.com", "www.pokemon.com",
    "onepiece-cardgame.kr", "www.onepiece-cardgame.kr",
    "www.onepiece-cardgame.com", "en.onepiece-cardgame.com",
    "www.naruto-cardgame.com",
}


def fetch(url: str) -> str:
    host = urllib.parse.urlparse(url).hostname
    if host not in ALLOWED:
        raise ValueError(f"unapproved host: {host}")
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read(3_000_000).decode("utf-8", "replace")


def textify(raw: str) -> str:
    raw = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw)).strip()


def iso_en(value: str) -> str:
    return dt.datetime.strptime(value, "%B %d, %Y").date().isoformat()


def collect_onepiece(url: str, region: str) -> list[dict]:
    text = textify(fetch(url))
    pattern = re.compile(r"(BOOSTER PACK\s*-[^-]{2,100}-\s*\[OP-\d+\]).{0,220}?Release Date\s*([A-Za-z]+\s+\d{1,2},\s+20\d{2}).{0,160}?MSRP\s*USD\s*\$([0-9.]+)", re.I)
    found = []
    for name, date, price in pattern.findall(text):
        found.append({"game":"ONE PIECE","region":region,"name":re.sub(r"\s+"," ",name).strip(),"release_date":iso_en(date),"price":f"${price}/팩","status":"출시예정","source":url})
    return found


def collect_onepiece_jp() -> list[dict]:
    """Read the Japanese booster listing; never label Asia-English data as JP."""
    url = "https://www.onepiece-cardgame.com/products/?subcategory=boosters"
    text = textify(fetch(url))
    pattern = re.compile(
        r"(?:ブースターパック|エクストラブースター|プレミアムブースター)\s*"
        r"(.{2,90}?)\s*〖(OP-\d+|EB-\d+|PRB-\d+)〗\s*"
        r"発売日\s*(20\d{2})\.(\d{1,2})\.(\d{1,2})(?:\([^)]*\))?\s*"
        r"メーカー希望小売価格\s*([0-9,]+)円",
        re.I,
    )
    found = []
    for title, code, y, m, d, price in pattern.findall(text):
        found.append({
            "game":"ONE PIECE", "region":"JP",
            "name":f"{title.strip()} [{code}]",
            "release_date":dt.date(int(y), int(m), int(d)).isoformat(),
            "price":f"¥{price}/팩", "status":"공식 확인", "source":url,
        })
    return found


def collect_onepiece_kr() -> list[dict]:
    url = "https://onepiece-cardgame.kr/products.do"
    text = textify(fetch(url))
    pattern = re.compile(r"\[(OPK-\d+|EBK-\d+)\]\s*(.{2,75}?)\s*(20\d{2}-\d{2}-\d{2}).{0,100}?\[1BOX\]\s*([0-9,]+)\s*원", re.I)
    found = []
    for code, title, date, price in pattern.findall(text):
        found.append({
            "game":"ONE PIECE", "region":"KR", "name":f"[{code}] {title.strip()}",
            "release_date":date, "price":f"₩{price}/BOX", "status":"공식 확인", "source":url,
        })
    return found


def collect_pokemon_jp() -> list[dict]:
    url = "https://www.pokemon-card.com/products/index.html?productType=expansion"
    text = textify(fetch(url))
    pattern = re.compile(r"(?:拡張パック|ハイクラスパック)\s*[「『]?(.{2,55}?)[」』]?\s*(?:拡張パック)?\s*販売日\s*(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日.{0,130}?希望小売価格\s*([0-9,]+)円")
    found = []
    for name, y, m, d, price in pattern.findall(text):
        date = dt.date(int(y), int(m), int(d)).isoformat()
        found.append({"game":"Pokémon","region":"JP","name":name.strip(),"release_date":date,"price":f"¥{price}/팩","status":"출시예정","source":url})
    return found


def collect_naruto() -> list[dict]:
    url = "https://www.naruto-cardgame.com/asia-en/"
    text = textify(fetch(url))
    if not re.search(r"(?:Summer\s+2027|Arriving\s+in\s+Summer\s+2027)", text, re.I):
        return []
    return [{"game":"NARUTO","region":"GLOBAL","name":"NARUTO CARD GAME","release_date":None,"release_window":"2027년 여름","price":"가격·제품 구성 미정","status":"전 세계 동시 출시 예정","source":url}]


def valid(item: dict) -> bool:
    if not all(item.get(k) for k in ("game", "region", "name", "source")):
        return False
    host_ok = urllib.parse.urlparse(item["source"]).hostname in ALLOWED
    if item.get("release_window") and not item.get("release_date"):
        return host_ok
    try:
        date = dt.date.fromisoformat(item["release_date"])
    except (TypeError, ValueError):
        return False
    return date >= dt.date.today() - dt.timedelta(days=45) and host_ok


def item_key(item: dict) -> tuple:
    return (item["game"], item["region"], item["name"], item.get("release_date") or item.get("release_window", ""))


def main() -> None:
    current = json.loads(DATA.read_text(encoding="utf-8"))
    candidates: list[dict] = []
    errors: list[str] = []
    collectors = [
        ("Pokémon JP", collect_pokemon_jp),
        ("ONE PIECE KR", collect_onepiece_kr),
        ("ONE PIECE JP", collect_onepiece_jp),
        ("ONE PIECE US", lambda: collect_onepiece("https://en.onepiece-cardgame.com/products/", "US")),
        ("NARUTO Global", collect_naruto),
    ]
    for label, collector in collectors:
        try:
            batch = collector()
            if not batch:
                raise RuntimeError("공식 페이지에서 검증 가능한 상품을 1건도 읽지 못함")
            candidates.extend(batch)
        except Exception as exc:
            errors.append(f"{label}: {type(exc).__name__}")

    merged = {item_key(x): x for x in current.get("items", []) if valid(x)}
    for item in candidates:
        if valid(item):
            merged[item_key(item)] = item

    current["items"] = sorted(merged.values(), key=lambda x: (x.get("release_date") or "9999-12-31", x["region"], x["name"]))
    current["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    current["collection_status"] = "정상" if not errors else "일부 출처 확인 실패"
    current["collection_errors"] = errors
    DATA.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

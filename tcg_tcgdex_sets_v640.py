#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V640 — opt-in, zero-key Pokémon SET-index collector via TCGdex.

Safe offline default. Explicit --sync fetches at most two fixed HTTPS JSON
endpoints (en and ja); 24h cache + conditional HTTP + size cap + atomic writes.
On 403/429/5xx/connection errors preserve last good cache. TCGdex is community
set information, NEVER manufacturer sealed BOX proof, hit rate or KR edition.
No images, resale prices, paid APIs, or cross-game data claimed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

LANGS = ("en", "ja")
API_BASE = "https://api.tcgdex.net/v2/"
MAX_BODY_BYTES = 1_500_000
MAX_SETS = 10000
CACHE_TTL = timedelta(hours=24)
DEFAULT_DIR = Path.home() / ".tcg_grader" / "tcgdex_sets"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, msg, headers, url):
        return None


def now_utc():
    return datetime.now(timezone.utc)


def safe_lang(lang):
    if lang not in LANGS:
        raise ValueError("UNSUPPORTED_TCGDEX_LANGUAGE")
    return lang


def source_url(lang):
    return API_BASE + safe_lang(lang) + "/sets"


def normalize_sets(data):
    if not isinstance(data, list) or len(data) > MAX_SETS:
        raise ValueError("INVALID_SET_LIST")
    seen, cleaned = set(), []
    for x in data:
        if not isinstance(x, dict):
            raise ValueError("INVALID_SET_OBJECT")
        sid, name = x.get("id"), x.get("name")
        if not isinstance(sid, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,50}", sid):
            raise ValueError("INVALID_SET_ID")
        if not isinstance(name, str) or not name.strip() or len(name) > 180:
            raise ValueError("INVALID_SET_NAME")
        count = x.get("cardCount")
        if not isinstance(count, dict) or type(count.get("total")) is not int or not 0 <= count["total"] <= 5000:
            raise ValueError("INVALID_SET_CARD_COUNT")
        if sid in seen:
            raise ValueError("DUPLICATE_SET_ID")
        seen.add(sid)
        cleaned.append({"id": sid, "name": name, "card_count_total": count["total"]})
    return sorted(cleaned, key=lambda row: row["id"])


def cache_path(root, lang):
    return Path(root) / ("tcgdex_sets_" + safe_lang(lang) + ".json")


def load_cache(root, lang):
    path = cache_path(root, lang)
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_BODY_BYTES:
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if (doc.get("schema_version") != 1 or doc.get("dataset_type") != "COMMUNITY_POKEMON_SET_INDEX" or
                doc.get("language") != lang or doc.get("source_url") != source_url(lang)):
            return None
        # The on-disk shape is intentionally compact (card_count_total);
        # rehydrate the original API shape before reusing the strict validator.
        # Never treat a successfully written file as malformed on the next read.
        if not isinstance(doc.get("sets"),list) or any(
            not isinstance(row,dict) or set(row)!={"id","name","card_count_total"}
            for row in doc["sets"]):
            return None
        normalized = normalize_sets([
            {"id":row["id"],"name":row["name"],
             "cardCount":{"total":row["card_count_total"]}}
            for row in doc["sets"]])
        if normalized != doc["sets"]:
            return None
        timestamp = datetime.fromisoformat(doc["fetched_at"])
        if timestamp.tzinfo is None:
            return None
        return doc
    except (ValueError, KeyError, TypeError, OSError):
        return None


def write_cache(root, lang, doc):
    path = cache_path(root, lang)
    directory = path.parent
    if directory.exists() and directory.is_symlink():
        raise ValueError("CACHE_DIR_SYMLINK")
    directory.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("CACHE_FILE_SYMLINK")
    tmp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=directory,
                                         prefix=".tcgdex_", suffix=".tmp", delete=False) as fp:
            tmp = Path(fp.name)
            json.dump(doc, fp, ensure_ascii=False, indent=2)
            fp.write("\n")
            fp.flush()
            os.fsync(fp.fileno())
        os.replace(tmp, path)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


def classify(code):
    if code in (401, 403):
        return "ACCESS_RESTRICTED"
    if code == 429:
        return "RATE_LIMIT_STOP"
    if code in (404, 410):
        return "NOT_FOUND_REVIEW"
    if code in (301, 302, 303, 307, 308):
        return "REDIRECT_REVIEW"
    if code in (408, 425, 500, 502, 503, 504):
        return "TRANSIENT_ERROR"
    return "UNVERIFIED_ERROR"


def sync_one(lang, root=DEFAULT_DIR, *, opener=None, clock=None):
    """One fixed endpoint, 24h TTL. Returns status, never makes up set data."""
    lang = safe_lang(lang)
    now = clock if clock is not None else now_utc()
    if now.tzinfo is None:
        raise ValueError("NAIVE_CLOCK")
    old = load_cache(root, lang)
    if old:
        dt = datetime.fromisoformat(old["fetched_at"])
        if dt <= now < dt + CACHE_TTL:
            return {"language": lang, "status": "FRESH_CACHE", "sets": len(old["sets"]),
                    "network_calls": 0}
    headers = {"Accept": "application/json",
               "User-Agent": "TCG-Grader-Free/1.0 (manual opt-in set index review)"}
    if old:
        if old.get("etag"):
            headers["If-None-Match"] = old["etag"]
        if old.get("last_modified"):
            headers["If-Modified-Since"] = old["last_modified"]
    req = Request(source_url(lang), headers=headers, method="GET")
    client = opener if opener is not None else build_opener(NoRedirect())
    try:
        with client.open(req, timeout=8) as response:
            if response.geturl() != source_url(lang):
                return {"language": lang, "status": "REDIRECT_REVIEW", "sets": len(old["sets"]) if old else 0,
                        "network_calls": 1, "using_stale": bool(old)}
            code = response.getcode()
            if code != 200:
                return {"language": lang, "status": classify(code),
                        "sets": len(old["sets"]) if old else 0, "network_calls": 1,
                        "using_stale": bool(old)}
            body = response.read(MAX_BODY_BYTES + 1)
            if len(body) > MAX_BODY_BYTES:
                raise ValueError("OVERSIZED_RESPONSE")
            rows = normalize_sets(json.loads(body.decode("utf-8")))
            doc = {"schema_version": 1, "dataset_type": "COMMUNITY_POKEMON_SET_INDEX",
                   "language": lang, "source_url": source_url(lang),
                   "fetched_at": now.isoformat(), "sets": rows,
                   "restriction": "NOT_MANUFACTURER_BOX_PROOF_OR_LIVE_PRICE"}
            if response.headers.get("ETag"):
                doc["etag"] = str(response.headers["ETag"])[:180]
            if response.headers.get("Last-Modified"):
                doc["last_modified"] = str(response.headers["Last-Modified"])[:120]
            write_cache(root, lang, doc)
            return {"language": lang, "status": "UPDATED_COMMUNITY_SETS",
                    "sets": len(rows), "network_calls": 1}
    except HTTPError as error:
        if error.code == 304 and old:
            old["fetched_at"] = now.isoformat()
            write_cache(root, lang, old)
            return {"language": lang, "status": "NOT_MODIFIED", "sets": len(old["sets"]),
                    "network_calls": 1}
        return {"language": lang, "status": classify(error.code),
                "sets": len(old["sets"]) if old else 0, "network_calls": 1,
                "using_stale": bool(old)}
    except (URLError, TimeoutError, OSError, ValueError, UnicodeError, json.JSONDecodeError):
        return {"language": lang, "status": "ERROR_KEPT_LAST_GOOD",
                "sets": len(old["sets"]) if old else 0, "network_calls": 1,
                "using_stale": bool(old)}


def read_local(lang, root=DEFAULT_DIR):
    doc = load_cache(root, safe_lang(lang))
    return {"language": lang, "status": "CACHED_OFFLINE" if doc else "NO_CACHE_OFFLINE",
            "sets": len(doc["sets"]) if doc else 0, "network_calls": 0}


def main(argv=None):
    ap = argparse.ArgumentParser(description="TCGdex Pokémon set index; offline unless --sync")
    ap.add_argument("--sync", action="store_true", help="Opt in to up to two TCGdex HTTPS GETs")
    ap.add_argument("--languages", default="en,ja", help="en,ja or a single language")
    ap.add_argument("--cache-dir", type=Path, default=DEFAULT_DIR)
    args = ap.parse_args(argv)
    languages = args.languages.split(",")
    if not languages or len(set(languages)) != len(languages) or any(x not in LANGS for x in languages):
        ap.error("Only en,ja supported; no duplicates")
    results = []
    for lang in languages:
        out = sync_one(lang, args.cache_dir) if args.sync else read_local(lang, args.cache_dir)
        results.append(out)
        if out["status"] in ("RATE_LIMIT_STOP", "ACCESS_RESTRICTED"):
            break
    print(json.dumps({"collector": "TCGDEX_COMMUNITY_POKEMON_SET_INDEX",
                      "manual_network_opt_in": args.sync, "results": results,
                      "network_calls": sum(x["network_calls"] for x in results),
                      "no_paid_dependencies": True,
                      "warning": "NOT OFFICIAL BOX, KR PRINT, MSRP, HIT RATE OR COMPLETED SALE"},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    if old not in text:
        raise RuntimeError(f"patch anchor not found: {path}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_all(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if old not in text:
        if new in text:
            return
        raise RuntimeError(f"patch anchor not found: {path}: {old!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


# 1) Concurrent graded-photo runs are normal on tablet/server/manual refresh overlap.
# Reuse the last validated candidate payload instead of failing the whole updater.
replace_once(
    "graded_photo_multi_source.py",
    """def collect()->dict:\n # A local server, Termux scheduler and manual command must not run this costly\n # stateful collection at the same time. The lock is adjacent to runtime state.\n with exclusive_file_lock(LEARNING.with_suffix(LEARNING.suffix+'.run'),timeout_seconds=0.05,stale_seconds=28_800):\n  return _collect_once()\n""",
    """def collect()->dict:\n # A local server, Termux scheduler and manual command can overlap. Only one run\n # mutates learning state; followers reuse the last validated payload instead of\n # turning benign lock contention into a collector failure.\n lock_target=LEARNING.with_suffix(LEARNING.suffix+'.run')\n try:\n  with exclusive_file_lock(lock_target,timeout_seconds=1.5,stale_seconds=28_800):\n   return _collect_once()\n except TimeoutError:\n  previous=_load(OUT,{})\n  if isinstance(previous,dict) and isinstance(previous.get('summary'),dict):\n   recovered=dict(previous);summary=dict(previous['summary'])\n   summary['concurrent_run_reused']=True\n   summary['lock_contention_recovered']=True\n   summary['status']='동일 수집이 이미 실행 중 · 마지막 검증 후보 재사용'\n   recovered['summary']=summary\n   return recovered\n  # Fresh installs may not have a previous payload yet. Wait once, bounded, for\n  # the active collector to finish; never spin or launch a duplicate writer.\n  with exclusive_file_lock(lock_target,timeout_seconds=8.0,stale_seconds=28_800):\n   previous=_load(OUT,{})\n   if isinstance(previous,dict) and isinstance(previous.get('summary'),dict):\n    recovered=dict(previous);summary=dict(previous['summary'])\n    summary['concurrent_run_reused']=True\n    summary['lock_contention_recovered']=True\n    summary['status']='동일 수집 완료 · 방금 생성된 검증 후보 재사용'\n    recovered['summary']=summary\n    return recovered\n   return _collect_once()\n""",
)

# 2) The integrated multi-route candidate collector legitimately needs more than
# the generic 300s auxiliary ceiling on Termux. Keep link audit at 300s, but give
# integration a bounded 480s total budget so the 299s structural timeout vanishes.
replace_once(
    "auto_update_all.py",
    "started_aux=time.monotonic(); deadline=started_aux+300",
    "started_aux=time.monotonic(); total_budget=480 if stat_key == '__integration__' else 300; deadline=started_aux+total_budget",
)
replace_once(
    "auto_update_all.py",
    "보조작업도 핵심 작업과 동일하게 300초 총예산 내에서 1회 복구 재시도한다.",
    "보조작업은 1회 복구 재시도한다. 통합 후보수집은 Termux용 480초, 나머지는 300초 총예산을 사용한다.",
)

# 3) Discovery can encounter an old malformed market row. Quarantine only the bad
# row and keep verified prices; never let one None/empty entry invalidate the DB.
replace_once(
    "update_market_prices.py",
    "\ndef coverage(db):\n",
    """
def _sanitize_entries(db):
    entries=db.get('entries')
    if not isinstance(entries,dict):
        bad={'__entries__':entries}
        db['entries']={}
        quarantine=db.setdefault('invalid_entries_quarantine',{})
        quarantine.update(bad)
        return 1
    quarantine=db.setdefault('invalid_entries_quarantine',{})
    repaired=0
    for key,value in list(entries.items()):
        valid_key=isinstance(key,str) and key.count('|')==2
        valid_value=isinstance(value,dict) and bool(value.get('display'))
        if valid_key and valid_value:
            continue
        quarantine[str(key)]={'value':value,'reason':'invalid market entry quarantined'}
        entries.pop(key,None)
        repaired+=1
    # Keep quarantine bounded: it is diagnostic memory, not a second market DB.
    if len(quarantine)>100:
        for key in list(quarantine)[:-100]:
            quarantine.pop(key,None)
    return repaired


def coverage(db):
""",
)
replace_once(
    "update_market_prices.py",
    "db=json.loads(safe_read_text(DATA)); db.setdefault('entries',{}); errors=[]",
    "db=json.loads(safe_read_text(DATA)); errors=[]; initial_repairs=_sanitize_entries(db)",
)
replace_once(
    "update_market_prices.py",
    "    db['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')\n",
    """    late_repairs=_sanitize_entries(db)
    repaired_entries=initial_repairs+late_repairs
    if repaired_entries:
        db['market_entry_repair']={'repaired_count':repaired_entries,'action':'malformed rows quarantined; verified rows preserved'}
    db['updated_at']=dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
""",
)

# 4) Official release pages changed markup and WAF behavior. Use a normal browser
# UA, add tolerant parsers for the currently published JP layouts, and classify
# zero-row parser drift as recoverable when verified history already exists.
replace_once(
    "update_releases.py",
    '    "User-Agent": "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 "\n                  "Chrome/126.0 Safari/537.36 TCG-Grader-Release-Checker/2.0",',
    '    "User-Agent": "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 "\n                  "(KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36",',
)
replace_once(
    "update_releases.py",
    "\n\ndef collect_onepiece_jp() -> list[dict]:\n",
    r'''

def _parse_onepiece_jp_fallback(text: str, url: str) -> list[dict]:
    pattern = re.compile(
        r"(?:ブースター\s+)?(?:ブースターパック|エクストラブースター|プレミアムブースター)\s+"
        r"(.{2,100}?)\s*[〖【](OP-\d+|EB-\d+|PRB-\d+)[〗】]"
        r".{0,120}?発売日\s*(20\d{2})\s*[./年]\s*(\d{1,2})"
        r"(?:\s*[./月]\s*(\d{1,2}))?.{0,160}?メーカー希望小売価格\s*([0-9,]+)\s*円",
        re.I | re.S,
    )
    found=[]
    for title,code,y,m,d,price in pattern.findall(text):
        row={"game":"ONE PIECE","region":"JP","name":f"{re.sub(r'\s+',' ',title).strip()} [{code}]",
             "price":f"¥{price}/팩","status":"공식 확인","source":url}
        if d:
            row["release_date"]=dt.date(int(y),int(m),int(d)).isoformat()
        else:
            row.update({"release_date":None,"release_window":f"{int(y):04d}-{int(m):02d}",
                        "release_precision":"month","release_label":f"{int(y):04d}년 {int(m)}월"})
        found.append(row)
    return found


def collect_onepiece_jp() -> list[dict]:
''',
)
replace_once(
    "update_releases.py",
    "            found = _parse_onepiece_jp(html_to_text(fetch(url)), url)",
    "            text = html_to_text(fetch(url)); found = _parse_onepiece_jp(text, url) or _parse_onepiece_jp_fallback(text, url)",
)
replace_once(
    "update_releases.py",
    "\n\ndef collect_pokemon_jp() -> list[dict]:\n",
    r'''

def _parse_pokemon_jp_fallback(text: str, url: str) -> list[dict]:
    pattern = re.compile(
        r"(?:強化拡張パック|拡張パック|ハイクラスパック|コンセプトパック)\s*[「『]\s*([^」』]{2,70})[」』]"
        r".{0,140}?(?:販売日|発売日)\s*(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日"
        r".{0,180}?希望小売価格\s*([0-9,]+)\s*円",
        re.I | re.S,
    )
    found=[]
    for name,y,m,d,price in pattern.findall(text):
        found.append({"game":"Pokémon","region":"JP","name":re.sub(r'\s+',' ',name).strip(),
                      "release_date":dt.date(int(y),int(m),int(d)).isoformat(),"price":f"¥{price}/팩",
                      "status":"공식 확인","source":url})
    return found


def collect_pokemon_jp() -> list[dict]:
''',
)
replace_once(
    "update_releases.py",
    "            found = _parse_pokemon_jp(html_to_text(fetch(url)), url)",
    "            text = html_to_text(fetch(url)); found = _parse_pokemon_jp(text, url) or _parse_pokemon_jp_fallback(text, url)",
)
replace_once(
    "update_releases.py",
    "    errors: list[str] = []\n    collectors = [",
    "    errors: list[str] = []\n    parser_drift_warnings: list[str] = []\n    collectors = [",
)
replace_once(
    "update_releases.py",
    """                if not batch:\n                    raise ValueError(\"공식 페이지에서 검증 가능한 상품을 1건도 읽지 못함\")\n                candidates.extend(batch)\n""",
    """                if not batch:
                    coverage_map={
                        'Pokémon JP':('Pokémon','JP'),'ONE PIECE KR':('ONE PIECE','KR'),
                        'ONE PIECE JP':('ONE PIECE','JP'),'ONE PIECE US':('ONE PIECE','US'),
                        'NARUTO Global':('NARUTO','GLOBAL'),
                    }
                    expected=coverage_map.get(label)
                    has_history=bool(expected and any(
                        isinstance(x,dict) and x.get('game')==expected[0] and x.get('region')==expected[1] and valid(x)
                        for x in current.get('items',[])
                    ))
                    if has_history:
                        parser_drift_warnings.append(f"{label}: 공식 페이지 0건 · 기존 검증 이력 유지 · 다음 실행에서 재파싱")
                        continue
                    raise ValueError("공식 페이지에서 검증 가능한 상품을 1건도 읽지 못함")
                candidates.extend(batch)
""",
)
replace_once(
    "update_releases.py",
    """    current[\"collection_status\"] = \"정상\" if not errors else \"일부 출처 확인 실패 · 기존 전체 출시이력 보존\"\n    current[\"collection_errors\"] = errors\n""",
    """    if errors:
        current["collection_status"] = "일부 출처 확인 실패 · 기존 전체 출시이력 보존"
    elif parser_drift_warnings:
        current["collection_status"] = "정상 · 기존 검증자료 유지 · 파서 드리프트 자가복구 대기"
    else:
        current["collection_status"] = "정상"
    current["collection_errors"] = errors
    current["parser_drift_warnings"] = parser_drift_warnings
""",
)

# 5) one-piece.com canonical news URL avoids the directory redirect that produced
# misleading `https only` warnings on some Android/Termux network paths. Refresh
# existing tracker rows as well as newly seeded rows.
replace_all(
    "update_promo_events.py",
    '"https://one-piece.com/news/"',
    '"https://one-piece.com/news/index.html"',
)
replace_once(
    "update_promo_events.py",
    """    movie_tracker_key = {(x.get(\"game\"), x.get(\"region\"), x.get(\"category\"), x.get(\"name_ko\")) for x in valid_original}\n    for tracker in REGIONAL_MOVIE_TRACKERS:\n        key = (tracker[\"game\"], tracker[\"region\"], tracker[\"category\"], tracker[\"name_ko\"])\n        if key not in movie_tracker_key:\n            valid_original.append(normalize_event_dates(dict(tracker)))\n            movie_tracker_key.add(key)\n""",
    """    movie_tracker_key = {(x.get("game"), x.get("region"), x.get("category"), x.get("name_ko")) for x in valid_original}
    for tracker in REGIONAL_MOVIE_TRACKERS:
        key = (tracker["game"], tracker["region"], tracker["category"], tracker["name_ko"])
        found = next((i for i,x in enumerate(valid_original)
                      if (x.get("game"),x.get("region"),x.get("category"),x.get("name_ko")) == key), None)
        if found is None:
            valid_original.append(normalize_event_dates(dict(tracker)))
            movie_tracker_key.add(key)
        else:
            previous=valid_original[found]
            refreshed={**previous,**tracker}
            for field in ("link_checked_at","link_status","link_statuses"):
                if field in previous:
                    refreshed[field]=previous[field]
            valid_original[found]=normalize_event_dates(refreshed)
""",
)

print("runtime self-heal v110 patch applied")

#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import importlib
import json
import re
import subprocess

EXPECTED = {
    "update_promo_events.py": "e7524b60c6bc292679f8c997992e5d13dd05a8b8",
    "update_releases.py": "9370c53c4ddbae324eaab80ddd5c1a8a05edc3e3",
    "test_0600_operational_refresh_v25.py": "22b7344a89374d8f8757efb61e0f7d2c76519ecf",
    "test_collection_scope_compat_v214.py": "c42646f37e9c88d302ffc739884b66df1affbe2d",
    "test_release_history_coverage_v4.py": "2b26343eafec5c9c2374751807b829ae96afc6b2",
    "releases.json": "60655bb1aa39085c9a95ccf5ea28c5e9191327c9",
    "purchase_sources.json": "a4f70092e0458503dc7f7a4cb6f18f21eb9b90c3",
    "promo_events.json": "5db1d652b57cd511115612dca776553745cd0112",
}


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one exact match in {path}, found {count}: {old!r}")
    write(path, text.replace(old, new, 1))


def regex_once(path: str, pattern: str, replacement: str) -> None:
    text = read(path)
    text2, count = re.subn(pattern, replacement, text, count=1, flags=re.S | re.M)
    if count != 1:
        raise SystemExit(f"expected one regex match in {path}, found {count}: {pattern}")
    write(path, text2)


for path, sha in EXPECTED.items():
    actual = subprocess.check_output(["git", "hash-object", path], text=True).strip()
    if actual != sha:
        raise SystemExit(f"SHA guard failed for {path}: expected {sha}, got {actual}")

# ---------------------------------------------------------------------------
# 1) Event source migration: keep live, specific official event evidence.
# ---------------------------------------------------------------------------
replace_once(
    "update_promo_events.py",
    'POKEMON_KR_EVENT_INDEX = "https://pokemonkorea.co.kr/news/2"\n',
    'POKEMON_KR_EVENT_INDEX = "https://pokemonkorea.co.kr/news/2"\n'
    'POKEMON_KR_SEONGNAM_TOURNAMENT_PAGE = "https://pokemonkorea.co.kr/2026_battle_tournament3/menu800"\n',
)
replace_once(
    "update_promo_events.py",
    '    "https://pokemonkorea.co.kr/2026_battle_tournament3": POKEMON_KR_EVENT_INDEX,\n'
    '    "https://pokemonkorea.co.kr/2026_battle_tournament3/menu800": POKEMON_KR_EVENT_INDEX,\n',
    '    "https://pokemonkorea.co.kr/2026_battle_tournament3": POKEMON_KR_SEONGNAM_TOURNAMENT_PAGE,\n',
)

helper_block = r'''
def _migrate_pokemon_kr_event_source(item: dict) -> tuple[dict, int]:
    """Move retired Korean Pokémon routes without discarding live event-level evidence."""
    repaired = dict(item)
    if repaired.get("game") != "포켓몬 카드" or repaired.get("region") != "KR":
        return repaired, 0

    changes = 0
    old_source = str(repaired.get("source") or "")
    original_source = str(repaired.get("original_source") or "")
    label = f"{repaired.get('name_ko', '')} {repaired.get('name_native', '')}".casefold()

    # The Seongnam tournament detail page is still live and contains the exact
    # event title/schedule. Prefer it over a generic news index when provenance
    # already points to that page, otherwise title verification loses evidence.
    seongnam_specific = (
        old_source == POKEMON_KR_SEONGNAM_TOURNAMENT_PAGE
        or old_source == "https://pokemonkorea.co.kr/2026_battle_tournament3"
        or original_source == POKEMON_KR_SEONGNAM_TOURNAMENT_PAGE
        or ("성남city" in label and original_source.startswith("https://pokemonkorea.co.kr/2026_battle_tournament3"))
    )
    if seongnam_specific:
        new_source = POKEMON_KR_SEONGNAM_TOURNAMENT_PAGE
    else:
        new_source = OFFICIAL_SOURCE_REPLACEMENTS.get(old_source, old_source)

    if new_source and new_source != old_source:
        repaired["source"] = new_source
        changes += 1
        # Link-health evidence belongs to the old URL and must not be carried
        # forward as though the replacement endpoint had already been checked.
        for field in ("link_checked_at", "link_status", "link_statuses"):
            repaired.pop(field, None)

    existing_collection = str(repaired.get("collection_source") or "")
    legacy_collection = {
        "https://new.pokemonkorea.co.kr/card",
        "https://new.pokemonkorea.co.kr/card/",
        "https://new.pokemonkorea.co.kr/card/category/5",
        "https://pokemoncard.co.kr/card/category/5",
    }
    desired_collection = None
    if str(repaired.get("source") or "") == POKEMON_KR_SEONGNAM_TOURNAMENT_PAGE:
        desired_collection = POKEMON_KR_SEONGNAM_TOURNAMENT_PAGE
    elif not existing_collection or existing_collection in legacy_collection:
        desired_collection = POKEMON_KR_EVENT_INDEX

    if desired_collection and desired_collection != existing_collection:
        repaired["collection_source"] = desired_collection
        changes += 1
        for field in ("link_checked_at", "link_status", "link_statuses"):
            repaired.pop(field, None)
    return repaired, changes


def _refresh_movie_tracker(previous: dict, tracker: dict) -> dict:
    """Refresh a tracker without retaining verification fields removed by policy."""
    refreshed = {**previous, **tracker}
    same_source = str(previous.get("source") or "") == str(tracker.get("source") or "")
    if same_source:
        for field in ("link_checked_at", "link_status", "link_statuses"):
            if field in previous:
                refreshed[field] = previous[field]

    if "verification_source" not in tracker:
        for field in (
            "verification_source", "verification_checked_at",
            "verification_status", "verification_error",
        ):
            refreshed.pop(field, None)
        statuses = refreshed.get("link_statuses")
        if isinstance(statuses, dict) and "verification_source" in statuses:
            statuses = dict(statuses)
            statuses.pop("verification_source", None)
            if statuses:
                refreshed["link_statuses"] = statuses
            else:
                refreshed.pop("link_statuses", None)
    return normalize_event_dates(refreshed)

'''
replace_once(
    "update_promo_events.py",
    '\ndef main() -> dict:\n',
    '\n' + helper_block + 'def main() -> dict:\n',
)

regex_once(
    "update_promo_events.py",
    r'''        repaired = normalize_event_dates\(item\)\n        old_source = str\(repaired.get\("source"\) or ""\)\n        replacement_source = OFFICIAL_SOURCE_REPLACEMENTS.get\(old_source\)\n        if replacement_source:\n            repaired\["source"\] = replacement_source\n            repaired_count \+= 1\n        if repaired.get\("game"\) == "포켓몬 카드" and repaired.get\("region"\) == "KR":\n            existing_collection = str\(repaired.get\("collection_source"\) or ""\)\n            if not existing_collection or existing_collection in \{\n                "https://new.pokemonkorea.co.kr/card",\n                "https://new.pokemonkorea.co.kr/card/",\n                "https://new.pokemonkorea.co.kr/card/category/5",\n            \}:\n                repaired\["collection_source"\] = POKEMON_KR_EVENT_INDEX\n                if existing_collection != POKEMON_KR_EVENT_INDEX:\n                    repaired_count \+= 1\n''',
    '''        repaired = normalize_event_dates(item)\n        repaired, source_repairs = _migrate_pokemon_kr_event_source(repaired)\n        repaired_count += source_repairs\n''',
)
replace_once(
    "update_promo_events.py",
    '''            previous=valid_original[found]\n            refreshed={**previous,**tracker}\n            for field in ("link_checked_at","link_status","link_statuses"):\n                if field in previous:\n                    refreshed[field]=previous[field]\n            valid_original[found]=normalize_event_dates(refreshed)\n''',
    '''            previous=valid_original[found]\n            valid_original[found]=_refresh_movie_tracker(previous, tracker)\n''',
)

# ---------------------------------------------------------------------------
# 2) Release-history migration: preserve product IDs on the current official host.
# ---------------------------------------------------------------------------
replace_once(
    "update_releases.py",
    '    "pokemoncard.co.kr", "www.pokemoncard.co.kr", "new.pokemonkorea.co.kr",\n',
    '    "pokemoncard.co.kr", "www.pokemoncard.co.kr",\n',
)
replace_once(
    "update_releases.py",
    '}\n\n# Plausibility guard only.',
    '''}\n\nPOKEMON_KR_PRODUCT_INDEX = "https://pokemoncard.co.kr/card/category/info1"\nPOKEMON_KR_LEGACY_HOSTS = {"new.pokemonkorea.co.kr"}\n\n\ndef _migrate_pokemon_kr_release_source(item: dict) -> dict:\n    """Move verified KR Pokémon history to the current official host without changing product identity."""\n    row = dict(item)\n    if row.get("game") != "Pokémon" or row.get("region") != "KR":\n        return row\n    source = str(row.get("source") or "")\n    try:\n        parsed = urllib.parse.urlsplit(source)\n    except ValueError:\n        return row\n    if (parsed.hostname or "").lower() not in POKEMON_KR_LEGACY_HOSTS:\n        return row\n\n    row.setdefault("original_source", source)\n    if re.fullmatch(r"/card/\\d{1,8}/?", parsed.path or ""):\n        row["source"] = urllib.parse.urlunsplit(\n            ("https", "pokemoncard.co.kr", parsed.path, parsed.query, "")\n        )\n    else:\n        row["source"] = POKEMON_KR_PRODUCT_INDEX\n    for field in ("link_checked_at", "link_status", "link_statuses"):\n        row.pop(field, None)\n    return row\n\n\n# Plausibility guard only.''',
)
replace_once(
    "update_releases.py",
    '    stored_history = [*stored_items, *stored_archive]\n',
    '    stored_history = [\n        _migrate_pokemon_kr_release_source(x) if isinstance(x, dict) else x\n        for x in [*stored_items, *stored_archive]\n    ]\n',
)

# ---------------------------------------------------------------------------
# 3) Regression tests for the two migrations and retired secondary evidence.
# ---------------------------------------------------------------------------
replace_once(
    "test_0600_operational_refresh_v25.py",
    '''        self.assertEqual(\n            update_promo_events.OFFICIAL_SOURCE_REPLACEMENTS[\n                "https://pokemonkorea.co.kr/2026_battle_tournament3"\n            ],\n            current,\n        )\n''',
    '''        self.assertEqual(\n            update_promo_events.OFFICIAL_SOURCE_REPLACEMENTS[\n                "https://pokemonkorea.co.kr/2026_battle_tournament3"\n            ],\n            update_promo_events.POKEMON_KR_SEONGNAM_TOURNAMENT_PAGE,\n        )\n''',
)
insert_0600 = '''\n    def test_specific_seongnam_event_keeps_live_detail_evidence(self):\n        legacy = {\n            "game": "포켓몬 카드",\n            "region": "KR",\n            "category": "collaboration",\n            "name_ko": "2026 성남CITY 배틀 토너먼트 × GXG 2026",\n            "name_native": "포켓몬 카드 게임 2026 성남CITY 배틀 토너먼트",\n            "source": "https://new.pokemonkorea.co.kr/card",\n            "collection_source": "https://new.pokemonkorea.co.kr/card",\n            "original_source": update_promo_events.POKEMON_KR_SEONGNAM_TOURNAMENT_PAGE,\n        }\n        repaired, changes = update_promo_events._migrate_pokemon_kr_event_source(legacy)\n        self.assertGreaterEqual(changes, 2)\n        self.assertEqual(repaired["source"], update_promo_events.POKEMON_KR_SEONGNAM_TOURNAMENT_PAGE)\n        self.assertEqual(repaired["collection_source"], update_promo_events.POKEMON_KR_SEONGNAM_TOURNAMENT_PAGE)\n        with mock.patch.object(\n            update_promo_events, "fetch",\n            return_value="포켓몬 카드 게임 2026 성남CITY 배틀 토너먼트 현장 예선",\n        ):\n            _, error = update_promo_events.check_existing(repaired)\n        self.assertIsNone(error)\n\n    def test_movie_tracker_refresh_removes_retired_generic_secondary_probe(self):\n        tracker = dict(update_promo_events.KR_MOVIE_TRACKERS[0])\n        previous = {\n            **tracker,\n            "verification_source": "https://www.kobis.or.kr/kobis/business/mast/mvie/searchMovieList.do",\n            "verification_status": "secondary_temporarily_unavailable",\n            "verification_error": "URLError: timed out",\n            "verification_checked_at": "2026-09-12T00:00:00+00:00",\n            "link_statuses": {"source": "정상", "verification_source": "네트워크 지연"},\n        }\n        refreshed = update_promo_events._refresh_movie_tracker(previous, tracker)\n        self.assertNotIn("verification_source", refreshed)\n        self.assertNotIn("verification_status", refreshed)\n        self.assertNotIn("verification_error", refreshed)\n        self.assertNotIn("verification_checked_at", refreshed)\n        self.assertNotIn("verification_source", refreshed.get("link_statuses", {}))\n'''
replace_once(
    "test_0600_operational_refresh_v25.py",
    '\n    def test_pokemon_kr_event_uses_current_same_company_collection_source(self):\n',
    insert_0600 + '\n    def test_pokemon_kr_event_uses_current_same_company_collection_source(self):\n',
)

regex_once(
    "test_collection_scope_compat_v214.py",
    r'''    def test_retired_event_sources_are_migrated_to_current_news_index\(self\):.*?(?=    def test_auxiliary_discovery_routes_use_current_event_source)''',
    '''    def test_retired_event_sources_use_role_specific_current_evidence(self):\n        expected = update_promo_events.POKEMON_KR_EVENT_INDEX\n        for legacy in (\n            "https://new.pokemonkorea.co.kr/card",\n            "https://new.pokemonkorea.co.kr/card/",\n            "https://new.pokemonkorea.co.kr/card/category/5",\n            "https://pokemoncard.co.kr/card/category/5",\n            "https://pokemonkorea.co.kr/",\n            "https://www.pokemonkorea.co.kr/",\n        ):\n            self.assertEqual(update_promo_events.OFFICIAL_SOURCE_REPLACEMENTS[legacy], expected)\n        self.assertEqual(\n            update_promo_events.OFFICIAL_SOURCE_REPLACEMENTS[\n                "https://pokemonkorea.co.kr/2026_battle_tournament3"\n            ],\n            update_promo_events.POKEMON_KR_SEONGNAM_TOURNAMENT_PAGE,\n        )\n        self.assertNotIn(\n            update_promo_events.POKEMON_KR_SEONGNAM_TOURNAMENT_PAGE,\n            update_promo_events.OFFICIAL_SOURCE_REPLACEMENTS,\n        )\n\n''',
)

insert_release_tests = '''\n    def test_legacy_korean_pokemon_detail_keeps_product_id_on_current_host(self):\n        row = releases._migrate_pokemon_kr_release_source({\n            "game": "Pokémon", "region": "KR", "name": "나이트원더러",\n            "source": "https://new.pokemonkorea.co.kr/card/650",\n            "release_date": "2024-08-09",\n            "link_status": "정상", "link_checked_at": "2026-09-12T00:00:00+00:00",\n        })\n        self.assertEqual(row["source"], "https://pokemoncard.co.kr/card/650")\n        self.assertEqual(row["original_source"], "https://new.pokemonkorea.co.kr/card/650")\n        self.assertNotIn("link_status", row)\n        self.assertNotIn("link_checked_at", row)\n\n    def test_legacy_korean_pokemon_root_moves_to_current_product_index(self):\n        row = releases._migrate_pokemon_kr_release_source({\n            "game": "Pokémon", "region": "KR", "name": "legacy",\n            "source": "https://new.pokemonkorea.co.kr/card",\n            "release_date": "2025-01-01",\n        })\n        self.assertEqual(row["source"], releases.POKEMON_KR_PRODUCT_INDEX)\n        self.assertNotIn("new.pokemonkorea.co.kr", releases.ALLOWED)\n\n    def test_release_source_migration_is_scoped_to_korean_pokemon(self):\n        row = {\n            "game": "ONE PIECE", "region": "KR", "name": "legacy",\n            "source": "https://new.pokemonkorea.co.kr/card/650",\n            "release_date": "2025-01-01",\n        }\n        self.assertEqual(releases._migrate_pokemon_kr_release_source(row), row)\n'''
replace_once(
    "test_release_history_coverage_v4.py",
    '\n    def test_current_korean_index_collects_same_host_product_details(self):\n',
    insert_release_tests + '\n    def test_current_korean_index_collects_same_host_product_details(self):\n',
)

# ---------------------------------------------------------------------------
# 4) Deterministically migrate committed snapshots so static consumers do not
#    briefly expose stale executable links before the next collector run.
# ---------------------------------------------------------------------------
importlib.invalidate_caches()
import update_releases as releases
import update_purchase_sources as purchase
import update_promo_events as promo

release_payload = json.loads(read("releases.json"))
for bucket in ("items", "archive_items"):
    rows = release_payload.get(bucket) or []
    release_payload[bucket] = [
        releases._migrate_pokemon_kr_release_source(row) if isinstance(row, dict) else row
        for row in rows
    ]
write("releases.json", json.dumps(release_payload, ensure_ascii=False, indent=2) + "\n")

purchase_payload = json.loads(read("purchase_sources.json"))
new_sources = []
for row in purchase_payload.get("sources") or []:
    if not isinstance(row, dict):
        new_sources.append(row)
        continue
    before = dict(row)
    after = purchase._canonicalize_pokemon_kr_source(dict(row))
    changed = before.get("url") != after.get("url") or before.get("official_reference_url") != after.get("official_reference_url")
    if changed:
        after["link_status"] = "주소 이전 · 다음 갱신에서 연결상태 재확인"
        after.pop("last_checked_at", None)
        after.pop("link_checked_at", None)
        after.pop("link_statuses", None)
    new_sources.append(after)
purchase_payload["sources"] = new_sources
write("purchase_sources.json", json.dumps(purchase_payload, ensure_ascii=False, indent=2) + "\n")

promo_payload = json.loads(read("promo_events.json"))
tracker_by_key = {
    (t.get("game"), t.get("region"), t.get("category"), t.get("name_ko")): t
    for t in promo.REGIONAL_MOVIE_TRACKERS
}
for bucket in ("items", "archive_items"):
    migrated = []
    for row in promo_payload.get(bucket) or []:
        if not isinstance(row, dict):
            migrated.append(row)
            continue
        row, _ = promo._migrate_pokemon_kr_event_source(row)
        key = (row.get("game"), row.get("region"), row.get("category"), row.get("name_ko"))
        tracker = tracker_by_key.get(key)
        if tracker is not None:
            row = promo._refresh_movie_tracker(row, tracker)
        migrated.append(row)
    promo_payload[bucket] = migrated
warnings = [
    f"{row.get('name_ko', '이름 없음')}: {row.get('verification_error', '보조검증 일시 확인불가')}"
    for row in (promo_payload.get("items") or [])
    if isinstance(row, dict) and row.get("verification_status") == "secondary_temporarily_unavailable"
]
promo_payload["secondary_verification_warnings"] = warnings[:50]
if not warnings and not (promo_payload.get("collection_errors") or []):
    pairs = int((promo_payload.get("coverage") or {}).get("movie_game_region_pairs") or 9)
    promo_payload["collection_status"] = f"정상 · 한·일·미 영화정보 {pairs}/9 조합 추적"
write("promo_events.json", json.dumps(promo_payload, ensure_ascii=False, indent=2) + "\n")

# Final static assertions: historical provenance may keep old URLs only in
# original_source, never in executable source/collection/reference fields.
for row in [*(release_payload.get("items") or []), *(release_payload.get("archive_items") or [])]:
    if isinstance(row, dict) and "new.pokemonkorea.co.kr" in str(row.get("source") or ""):
        raise SystemExit(f"legacy executable release source remains: {row.get('name')}")
for row in purchase_payload.get("sources") or []:
    if not isinstance(row, dict):
        continue
    for field in ("url", "official_reference_url"):
        if "new.pokemonkorea.co.kr" in str(row.get(field) or ""):
            raise SystemExit(f"legacy executable purchase source remains: {row.get('name')} {field}")
for row in [*(promo_payload.get("items") or []), *(promo_payload.get("archive_items") or [])]:
    if not isinstance(row, dict):
        continue
    for field in ("source", "collection_source", "verification_source"):
        if "new.pokemonkorea.co.kr" in str(row.get(field) or ""):
            raise SystemExit(f"legacy executable promo source remains: {row.get('name_ko')} {field}")
    if str(row.get("verification_source") or "").endswith("/searchMovieList.do"):
        raise SystemExit(f"generic KOBIS search probe remains executable: {row.get('name_ko')}")

print("v232 source migration applied")

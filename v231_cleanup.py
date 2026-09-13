#!/usr/bin/env python3
from pathlib import Path
import re
import subprocess

EXPECTED = {
    "multi_route_event_discovery.py": "5a0f9f1ae7521ea2e39141b2475367357d997abe",
    "social_event_discovery.py": "2524f5bd2bb2ef0f6ab22bb484465aa70346d408",
    "validate_external_links.py": "69ef572fe8c461a204bdb06fca6d56081d0c3e9a",
    "tcg_updater.py": "835e3fcf6ffdc45a6f9ade2ed05282fa6d517df3",
    "test_0600_operational_refresh_v25.py": "98fe25f8d46a6b9c950e4a8eb2e43be76e47f0cc",
    "test_collection_scope_compat_v214.py": "eefcadcb00c4ca3430561bd29a7277abbba7d3a7",
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

CURRENT_EVENT = "https://pokemonkorea.co.kr/news/2"
PRODUCT_INDEX = "https://pokemoncard.co.kr/card/category/info1"
LEGACY = "https://new.pokemonkorea.co.kr/card"

replace_once(
    "multi_route_event_discovery.py",
    '    ("포켓몬 카드", "KR"): (\n        "https://new.pokemonkorea.co.kr/card",\n    ),',
    '    ("포켓몬 카드", "KR"): (\n        "https://pokemonkorea.co.kr/news/2",\n    ),',
)

replace_once(
    "social_event_discovery.py",
    '    "new.pokemonkorea.co.kr",\n',
    '    "pokemonkorea.co.kr", "www.pokemonkorea.co.kr",\n    "pokemoncard.co.kr", "www.pokemoncard.co.kr",\n',
)
replace_once(
    "social_event_discovery.py",
    '    ("포켓몬 카드", "KR", "https://new.pokemonkorea.co.kr/card"),',
    '    ("포켓몬 카드", "KR", "https://pokemonkorea.co.kr/news/2"),',
)

replace_once(
    "validate_external_links.py",
    ' "pokemoncard.co.kr":"https://new.pokemonkorea.co.kr/card",\n "www.pokemoncard.co.kr":"https://new.pokemonkorea.co.kr/card",\n "pokemonkorea.co.kr":"https://new.pokemonkorea.co.kr/card",\n "www.pokemonkorea.co.kr":"https://new.pokemonkorea.co.kr/card",\n',
    ' "pokemoncard.co.kr":"https://pokemoncard.co.kr/card/category/info1",\n "www.pokemoncard.co.kr":"https://pokemoncard.co.kr/card/category/info1",\n',
)

replace_once(
    "tcg_updater.py",
    "    'current':0,'total':7,'label':'대기 중','file':None,'message':'대기 중',",
    "    'current':0,'total':0,'label':'대기 중','file':None,'message':'대기 중',",
)
replace_once(
    "tcg_updater.py",
    "def _job_snapshot():\n    with UPDATE_JOB_LOCK:\n        return copy.deepcopy(UPDATE_JOB)\n",
    "def _job_snapshot():\n    with UPDATE_JOB_LOCK:\n        snapshot=copy.deepcopy(UPDATE_JOB)\n    # Idle state has no active step yet; expose the live job-count SSOT instead of a stale banner count.\n    if int(snapshot.get('total') or 0) <= 0:\n        snapshot['total']=_full_update_job_count()\n    return snapshot\n",
)

regex_once(
    "test_0600_operational_refresh_v25.py",
    r"^    def test_tracking_secondary_timeout_is_warning_not_hard_collection_error\(self\):.*?(?=^    def test_tracking_secondary_configuration_error_remains_fail_closed)",
    '''    def test_tracking_secondary_timeout_is_warning_not_hard_collection_error(self):
        tracker = dict(update_promo_events.KR_MOVIE_TRACKERS[2])
        tracker["verification_source"] = (
            "https://www.kobis.or.kr/kobis/business/mast/mvie/searchMovieDtl.do?movieCd=synthetic"
        )
        with mock.patch.object(
            update_promo_events,
            "fetch",
            side_effect=["official primary ok", OSError("timed out")],
        ):
            checked, error = update_promo_events.check_existing(tracker)
        self.assertIsNone(error)
        self.assertEqual(checked["source"], "https://naruto-official.com/en/news/01_2649")
        self.assertEqual(checked["verification_status"], "secondary_temporarily_unavailable")
        self.assertIn("timed out", checked["verification_error"].lower())

''',
)
regex_once(
    "test_0600_operational_refresh_v25.py",
    r"^    def test_tracking_secondary_configuration_error_remains_fail_closed\(self\):.*?(?=^    def test_retired_pokemon_routes_are_replaced)",
    '''    def test_tracking_secondary_configuration_error_remains_fail_closed(self):
        tracker = dict(update_promo_events.KR_MOVIE_TRACKERS[2])
        tracker["verification_source"] = (
            "https://www.kobis.or.kr/kobis/business/mast/mvie/searchMovieDtl.do?movieCd=synthetic"
        )
        with mock.patch.object(
            update_promo_events,
            "fetch",
            side_effect=["official primary ok", ValueError("unapproved verification url")],
        ):
            _, error = update_promo_events.check_existing(tracker)
        self.assertIsNotNone(error)
        self.assertIn("보조검증", error)

''',
)
regex_once(
    "test_0600_operational_refresh_v25.py",
    r"^    def test_retired_pokemon_routes_are_replaced\(self\):.*?(?=^    def test_pokemon_kr_event_uses_same_company_collection_fallback)",
    '''    def test_retired_pokemon_routes_are_replaced(self):
        current = update_promo_events.POKEMON_KR_EVENT_INDEX
        self.assertEqual(update_promo_events.INDEXES[2][2], current)
        self.assertEqual(
            update_promo_events.OFFICIAL_SOURCE_REPLACEMENTS[
                "https://pokemonkorea.co.kr/2026_battle_tournament3"
            ],
            current,
        )
        self.assertNotIn("new.pokemonkorea.co.kr", update_promo_events.ALLOWED)

''',
)
regex_once(
    "test_0600_operational_refresh_v25.py",
    r"^    def test_pokemon_kr_event_uses_same_company_collection_fallback\(self\):.*?(?=^    def test_factual_exchange_writers_use_atomic_runtime_helper)",
    '''    def test_pokemon_kr_event_uses_current_same_company_collection_source(self):
        tracker = dict(update_promo_events.KR_MOVIE_TRACKERS[0])
        current = update_promo_events.POKEMON_KR_EVENT_INDEX
        self.assertEqual(tracker["source"], current)
        self.assertEqual(tracker["collection_source"], current)
        self.assertNotIn("verification_source", tracker)
        with mock.patch.object(
            update_promo_events,
            "fetch",
            return_value="official collection page ok",
        ) as mocked:
            checked, error = update_promo_events.check_existing(tracker)
        self.assertIsNone(error)
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(mocked.call_args.args[0], current)
        self.assertNotIn("verification_status", checked)

    def test_idle_update_status_uses_runtime_job_count(self):
        snapshot = tcg_updater._job_snapshot()
        self.assertEqual(len(auto_update_all.JOBS), 8)
        self.assertEqual(snapshot["total"], len(auto_update_all.JOBS))

''',
)

regex_once(
    "test_collection_scope_compat_v214.py",
    r"^    def test_auxiliary_discovery_legacy_routes_are_visible_until_migrated\(self\):.*?(?=^    def test_link_audit_legacy_fallback_is_explicitly_visible_until_migrated)",
    '''    def test_auxiliary_discovery_routes_use_current_event_source(self):
        current = update_promo_events.POKEMON_KR_EVENT_INDEX
        self.assertEqual((current,), multi_route_event_discovery.OFFICIAL_ROUTES[("포켓몬 카드", "KR")])
        pages = {row[:2]: row[2] for row in social_event_discovery.OFFICIAL_DISCOVERY_PAGES}
        self.assertEqual(current, pages[("포켓몬 카드", "KR")])
        self.assertIn("pokemonkorea.co.kr", social_event_discovery.OFFICIAL_HOSTS)
        self.assertNotIn("new.pokemonkorea.co.kr", social_event_discovery.OFFICIAL_HOSTS)

''',
)
regex_once(
    "test_collection_scope_compat_v214.py",
    r"^    def test_link_audit_legacy_fallback_is_explicitly_visible_until_migrated\(self\):.*?(?=^\nif __name__ == \"__main__\":)",
    '''    def test_link_audit_uses_role_safe_current_fallbacks(self):
        product = update_purchase_sources.POKEMON_KR_PRODUCT_INDEX
        self.assertEqual(validate_external_links.FALLBACKS["pokemoncard.co.kr"], product)
        self.assertEqual(validate_external_links.FALLBACKS["www.pokemoncard.co.kr"], product)
        self.assertNotIn("pokemonkorea.co.kr", validate_external_links.FALLBACKS)
        self.assertNotIn("www.pokemonkorea.co.kr", validate_external_links.FALLBACKS)
        self.assertNotIn(
            "new.pokemonkorea.co.kr",
            " ".join(validate_external_links.FALLBACKS.values()),
        )
''',
)

for path in ("multi_route_event_discovery.py", "social_event_discovery.py", "validate_external_links.py"):
    text = read(path)
    if LEGACY in text or "new.pokemonkorea.co.kr" in text:
        raise SystemExit(f"legacy live route still present in {path}")
if "'total':7" in read("tcg_updater.py"):
    raise SystemExit("legacy 7-stage idle status still present")
if CURRENT_EVENT not in read("multi_route_event_discovery.py"):
    raise SystemExit("current Pokemon KR event route missing")
if PRODUCT_INDEX not in read("validate_external_links.py"):
    raise SystemExit("current Pokemon KR product fallback missing")

print("v231 bounded cleanup applied")

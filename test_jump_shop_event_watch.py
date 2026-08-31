import json
import unittest
from pathlib import Path

import multi_route_event_discovery as routes
import update_promo_events as updater


ROOT = Path(__file__).resolve().parent
SOURCE = "https://x.com/smg_comic/status/2081560207646441942"


class JumpShopEventWatchTests(unittest.TestCase):
    def test_verified_event_is_registered_for_both_supported_games(self):
        data = json.loads((ROOT / "promo_events.json").read_text(encoding="utf-8"))
        rows = [row for row in data.get("items", []) if row.get("source") == SOURCE]
        self.assertEqual({row.get("game") for row in rows}, {"원피스 카드", "나루토 카드"})
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row.get("start_date"), "2026-09-23")
            self.assertEqual(row.get("end_date"), "2026-10-06")
            self.assertIn("신세계백화점 강남점", row.get("location", ""))
            self.assertEqual(row.get("event_scope"), "licensed_ip_popup_not_tcg_tournament")
            self.assertIn("카드 프로모 증정은 공식 공지에서 별도 확인되지 않음", row.get("reward", ""))
            self.assertTrue(updater.valid(row))

    def test_only_exact_verified_social_post_is_allowed(self):
        self.assertEqual(updater.approved_url(SOURCE), SOURCE)
        for url in (
            "https://x.com/other/status/2081560207646441942",
            "https://x.com/smg_comic/status/1",
            "https://x.com/smg_comic",
        ):
            with self.assertRaises(ValueError):
                updater.approved_url(url)

    def test_korean_popup_search_has_jump_shop_terms(self):
        query = routes._query("원피스 카드", "KR", topic="popup")
        self.assertIn("점프샵", query)
        self.assertIn("JUMP SHOP", query)

    def test_official_account_is_scoped_to_both_games(self):
        data = json.loads((ROOT / "social_source_registry.json").read_text(encoding="utf-8"))
        rows = [row for row in data.get("accounts", []) if row.get("username") == "smg_comic"]
        self.assertEqual({row.get("game") for row in rows}, {"원피스 카드", "나루토 카드"})
        self.assertTrue(all(row.get("trusted") and row.get("manual") for row in rows))

    def test_publisher_and_department_store_are_discovery_only(self):
        for host in ("seoulmediacomics.com", "www.seoulmediacomics.com", "shinsegae.com", "www.shinsegae.com"):
            self.assertIn(host, routes.PARTNER_HOSTS)
            self.assertNotIn(host, routes.OFFICIAL_HOSTS)


if __name__ == "__main__":
    unittest.main()

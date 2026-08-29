import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class PlaygoEventWatchTests(unittest.TestCase):
    def test_community_watch_is_not_trusted(self):
        data = json.loads((ROOT / "social_source_registry.json").read_text(encoding="utf-8"))
        row = next(x for x in data.get("watch_accounts", []) if x.get("username") == "onepiececard_news")
        self.assertFalse(row.get("trusted"))
        self.assertEqual(row.get("role"), "community_watch")

    def test_social_search_has_playgo_terms_and_watch_accounts(self):
        text = (ROOT / "social_event_discovery.py").read_text(encoding="utf-8")
        self.assertIn("PLAYGO", text)
        self.assertIn("watch_accounts", text)
        self.assertIn("신사황", text)
        self.assertIn("playgo.bandainamcokorea.co.kr", text)

    def test_official_topics_and_seed_are_present(self):
        text = (ROOT / "update_promo_events.py").read_text(encoding="utf-8")
        self.assertIn("https://onepiece-cardgame.kr/topics.do", text)
        self.assertIn("brdno=6516", text)
        self.assertIn("PLAYGO 출시 알림 · 신사황 프로모션 팩 재배포", text)
        self.assertIn("playgo.bandainamcokorea.co.kr", text)


if __name__ == "__main__":
    unittest.main()

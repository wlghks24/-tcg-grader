#!/usr/bin/env python3
import urllib.parse
import unittest

import multi_channel_agent
import multi_route_event_discovery as routes
import social_event_discovery as social


class ExtendedDiscoveryChannelsV5Tests(unittest.TestCase):
    def test_multichannel_event_vocab_covers_challenge_style_announcements(self):
        expected = {
            "KR": ("챌린지", "개최"),
            "JP": ("チャレンジ", "開催"),
            "US": ("challenge", "distribution"),
        }
        for region, terms in expected.items():
            values = {str(x).lower() for x in multi_channel_agent.MultiChannelCollector.EVENT_OR[region]}
            for term in terms:
                self.assertIn(term.lower(), values)

    def test_multi_route_event_vocab_covers_challenge_style_announcements(self):
        self.assertIn("챌린지", routes.QUERY_FAMILIES["ko"]["event"])
        self.assertIn("チャレンジ", routes.QUERY_FAMILIES["ja"]["event"])
        self.assertIn("challenge", routes.QUERY_FAMILIES["en"]["event"].lower())

    def test_tiktok_and_twitch_are_discovery_only_social_hosts(self):
        self.assertIn("www.tiktok.com", social.SOCIAL_HOSTS)
        self.assertIn("www.twitch.tv", social.SOCIAL_HOSTS)
        self.assertEqual(social._parse_social_link("https://www.tiktok.com/@pokemon"), ("tiktok", "pokemon"))
        self.assertEqual(social._parse_social_link("https://www.twitch.tv/pokemontcg"), ("twitch", "pokemontcg"))

    def test_public_social_fallback_queries_tiktok_and_twitch_without_network(self):
        captured = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self, _limit):
                return b""

        def fake_urlopen(req, **_kwargs):
            captured["url"] = req.full_url
            return Response()

        original = social.safe_urlopen
        social.safe_urlopen = fake_urlopen
        try:
            rows, error = social._ddg_social_one(
                "나루토 카드", "JP", {"watch_accounts": []}, None
            )
        finally:
            social.safe_urlopen = original

        self.assertEqual(rows, [])
        self.assertIsNone(error)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(captured["url"]).query)["q"][0]
        self.assertIn("site:tiktok.com", query)
        self.assertIn("site:twitch.tv", query)

    def test_new_social_hosts_never_gain_trust_from_host_alone(self):
        rows = social._annotate_social_rows([
            {
                "game": "포켓몬 카드",
                "region": "US",
                "title": "Pokemon TCG community stream",
                "source": "https://www.twitch.tv/randomcollector",
                "source_kind": "twitch_public_search",
                "confidence": 0.60,
            }
        ], {"accounts": [], "watch_accounts": []})
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["verified"])
        self.assertFalse(rows[0]["official_account_verified"])
        self.assertTrue(rows[0]["fan_candidate"])
        self.assertEqual(rows[0]["source_tier"], "C-community")


if __name__ == "__main__":
    unittest.main()

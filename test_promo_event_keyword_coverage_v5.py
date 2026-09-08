#!/usr/bin/env python3
import unittest

import update_promo_events as promo


class PromoEventKeywordCoverageV5Tests(unittest.TestCase):
    def test_recent_japanese_sns_challenge_title_is_discoverable(self):
        title = "NARUTO＆BORUTO 忍里 SNSチャレンジ 9月5日より開催"
        self.assertIsNotNone(promo.EVENT_WORDS.search(title))

    def test_pokemon_run_participation_promo_terms_are_discoverable(self):
        samples = (
            "포켓몬 RUN 30 완주자 피카츄 프로모 카드",
            "Pokémon RUN 30 finisher promo card for participants",
            "Pokemon RUN 30 participation reward",
            "Pokémon RUN 30 完走 参加特典",
        )
        for value in samples:
            with self.subTest(value=value):
                self.assertIsNotNone(promo.EVENT_WORDS.search(value))

    def test_pokemon_run_seed_preserves_region_members_and_korea_exclusion(self):
        rows = [
            row for row in promo.OFFICIAL_VERIFIED_SEEDS
            if row.get("event_scope") == "official_asia_participation_promo"
        ]
        self.assertEqual(1, len(rows))
        row = rows[0]
        self.assertEqual("ASIA", row["region"])
        self.assertTrue(row["reward_watch"])
        self.assertTrue(row["must_show_candidate"])
        self.assertFalse(row["korea_included"])
        self.assertEqual(["KR"], row["excluded_regions"])
        self.assertEqual({"PH", "TW", "SG", "MY", "ID", "TH", "HK"}, set(row["region_members"]))

    def test_all_seven_pokemon_30th_asia_portals_are_directly_scanned(self):
        hosts = {
            promo.urllib.parse.urlsplit(url).hostname
            for region, game, url in promo.INDEXES
            if region == "ASIA" and game == "포켓몬 카드"
        }
        for host in (
            "tw.portal-pokemon.com", "hk.portal-pokemon.com",
            "sg.portal-pokemon.com", "my.portal-pokemon.com",
            "ph.portal-pokemon.com", "th.portal-pokemon.com",
            "id.portal-pokemon.com",
        ):
            self.assertIn(host, hosts)

    def test_challenge_terms_are_covered_across_supported_languages(self):
        samples = (
            "나루토 SNS 챌린지 행사",
            "NARUTO SNS Challenge starts September 5",
            "忍里チャレンジ開催",
        )
        for value in samples:
            with self.subTest(value=value):
                self.assertIsNotNone(promo.EVENT_WORDS.search(value))


if __name__ == "__main__":
    unittest.main()

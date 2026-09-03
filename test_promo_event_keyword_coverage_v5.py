#!/usr/bin/env python3
import unittest

import update_promo_events as promo


class PromoEventKeywordCoverageV5Tests(unittest.TestCase):
    def test_recent_japanese_sns_challenge_title_is_discoverable(self):
        title = "NARUTO＆BORUTO 忍里 SNSチャレンジ 9月5日より開催"
        self.assertIsNotNone(promo.EVENT_WORDS.search(title))

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

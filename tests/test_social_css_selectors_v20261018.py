"""Regression for CSS pseudo selectors and conditional rules in event ingestion."""
from __future__ import annotations

import unittest

import social_event_discovery as events


def candidate(title: str) -> dict:
    return {
        "game": "나루토 카드",
        "region": "JP",
        "category": "event",
        "topic": "event",
        "source": "https://naruto-official.com/news",
        "source_kind": "official_web",
        "title": title,
        "excerpt": "공식 행사 공지",
        "confidence": 0.94,
        "verified": True,
    }


class StylesheetSelectorsRegression(unittest.TestCase):
    def test_detects_css_selector_and_at_rules(self):
        snippets = (
            ".css-1od4a9n{width:24px}",
            ".css-1od4a9n:hover{width:24px}",
            ".css-abcd::before{content:''}",
            ".css-abcd > span {display:none}",
            "@media screen and (min-width: 600px){body{display:none}}",
            "@supports (display:grid){body{display:grid}}",
            ":root { --brand: #abc; }",
        )
        for text in snippets:
            with self.subTest(text=text):
                self.assertTrue(events._css_noise(text))
                self.assertEqual(events.merge_candidates([candidate(text)]), [])

    def test_legitimate_event_titles_still_allowed(self):
        titles = (
            "나루토 카드 공식 대회 안내",
            "행사에서 CSS 디자인을 소개했습니다",
            "포켓몬 카드 신규 콜라보!",
        )
        for title in titles:
            with self.subTest(title=title):
                self.assertFalse(events._css_noise(title))

    def test_hostile_nested_selector_tail_is_bounded(self):
        # Regression for CodeQL's ReDoS warning on nested optional selectors.
        # The scanner must not depend on nesting depth, and an unfinished
        # selector must never be promoted into a legitimate event candidate.
        suffix = ":not(" * 180
        for marker in (".css-abcd", "@media screen", "@supports (display:grid)"):
            with self.subTest(marker=marker):
                self.assertFalse(events._css_noise(marker + suffix))
                self.assertTrue(events._css_noise(marker + suffix + "{color:red}"))

    def test_css_mentions_without_stylesheets_are_valid(self):
        for title in (
            "New CSS collection announced for Pokémon cards",
            "Guide: What does .css-abc123 mean on a website?",
            "행사에서는 CSS와 미디어 기술을 설명합니다",
        ):
            with self.subTest(title=title):
                self.assertFalse(events._css_noise(title))

    def test_previous_css_candidate_not_retained(self):
        previous = {
            "items": [
                candidate(".css-1od4a9n:hover{width:24px}"),
                candidate("나루토 카드 공식 대회 안내"),
            ]
        }
        kept = events._previous_rows(previous)
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0]["title"], "나루토 카드 공식 대회 안내")


if __name__ == "__main__":
    unittest.main()

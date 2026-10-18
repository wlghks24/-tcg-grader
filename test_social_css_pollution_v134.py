"""Regression for verified-looking CSS fragments in collected TCG events."""
from __future__ import annotations
import unittest
import social_event_discovery as src

CSS = ".css-1od4a9n{width:24px;height:24px;filter:drop-shadow(0 0 2px #333)}"


def row(title: str, excerpt: str = "대회 공식 일정 공지") -> dict:
    return {
        "game": "나루토 카드", "region": "JP", "category": "event",
        "topic": "event", "source": "https://naruto-official.com/news",
        "source_kind": "official_web", "title": title, "excerpt": excerpt,
        "confidence": 0.94, "verified": True,
    }


class SocialCssPollutionGuardTests(unittest.TestCase):
    def test_css_class_block_is_detected(self):
        self.assertTrue(src._css_noise(CSS))

    def test_css_root_block_is_detected(self):
        self.assertTrue(src._css_noise(":root { --brand: #abc; }"))

    def test_html_style_tag_is_detected(self):
        self.assertTrue(src._css_noise("<style>.css-abc{display:none}</style>"))

    def test_article_about_css_is_not_blocked(self):
        self.assertFalse(src._css_noise("행사에서 CSS 디자인을 소개했습니다"))

    def test_verified_bad_candidate_is_rejected(self):
        self.assertEqual(src.merge_candidates([row(CSS)]), [])

    def test_valid_event_remains(self):
        result = src.merge_candidates([row("나루토 카드 공식 대회 개최")])
        self.assertEqual(len(result), 1)

    def test_valid_title_with_css_excerpt_is_salvaged(self):
        result = src.merge_candidates([row("나루토 카드 행사", CSS)])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["excerpt"], "")

    def test_bad_verified_previous_is_not_preserved(self):
        result = src._previous_rows({"items": [row(CSS), row("나루토 공식 이벤트")]})
        self.assertEqual(len(result), 1)
        self.assertIn("공식 이벤트", result[0]["title"])

if __name__ == "__main__":
    unittest.main()

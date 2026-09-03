import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import source_gap_intelligence as gap


class SourceGapIntelligenceTests(unittest.TestCase):
    def test_expected_matrix_is_three_games_three_regions_ten_topics(self):
        self.assertEqual(len(gap.EXPECTED_CELLS), 90)
        self.assertEqual(set(gap.GAMES), {"포켓몬 카드", "원피스 카드", "나루토 카드"})
        self.assertEqual(set(gap.REGIONS), {"KR", "JP", "US"})

    def test_source_families_cover_requested_discovery_routes(self):
        cases = [
            ({"source": "https://x.com/example/status/1"}, "social_x"),
            ({"source": "https://www.instagram.com/p/example/"}, "social_instagram"),
            ({"source": "https://www.youtube.com/watch?v=1"}, "social_youtube"),
            ({"source": "https://news.google.com/rss/articles/1"}, "google"),
            ({"source": "https://namu.wiki/w/example"}, "secondary_wiki"),
            ({"source": "https://www.reddit.com/r/pkmntcg/comments/example"}, "community"),
            ({"source": "https://blog.naver.com/example/1"}, "community"),
        ]
        for row, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(gap.classify_source(row), expected)

    def test_social_or_wiki_candidate_never_closes_verified_gap(self):
        social = {"items": [{
            "game": "포켓몬 카드", "region": "KR", "topic": "promo",
            "title": "프로모 행사 후보", "source": "https://x.com/example/status/1",
            "verified": False, "cross_checked": True,
        }]}
        supplementary = {"items": [{
            "game": "포켓몬 카드", "region": "KR", "topic": "promo",
            "title": "나무위키 후보", "source": "https://namu.wiki/w/example",
            "source_tier": "C", "verified": True,
        }]}
        audit = gap.audit_pipeline(social, supplementary, [])
        cell = next(x for x in audit["cells"] if x["game"] == "포켓몬 카드" and x["region"] == "KR" and x["topic"] == "promo")
        self.assertEqual(cell["verified_count"], 0)
        self.assertTrue(cell["lead_without_official_confirmation"])
        self.assertGreater(cell["risk_score"], 0)

    def test_explicit_official_verification_closes_gap(self):
        social = {"items": [{
            "game": "원피스 카드", "region": "JP", "topic": "event",
            "title": "공식 행사", "source": "https://www.onepiece-cardgame.com/events/",
            "source_grade": "official", "official_domain_match": True, "verified": True,
        }]}
        audit = gap.audit_pipeline(social, {}, [])
        cell = next(x for x in audit["cells"] if x["game"] == "원피스 카드" and x["region"] == "JP" and x["topic"] == "event")
        self.assertEqual(cell["verified_count"], 1)
        self.assertFalse(cell["lead_without_official_confirmation"])
        self.assertEqual(cell["risk_score"], 0)

    def test_observe_learns_utility_but_primary_verification_stays_first(self):
        social = {"items": [
            {
                "game": "나루토 카드", "region": "US", "topic": "release",
                "title": "official release", "source": "https://www.naruto-cardgame.com/en/",
                "official_domain_match": True, "source_grade": "official", "verified": True,
            },
            {
                "game": "나루토 카드", "region": "US", "topic": "release",
                "title": "community lead", "source": "https://www.reddit.com/r/example/comments/1",
                "verified": False, "cross_checked": True,
            },
        ], "channel_status": {}}
        with tempfile.TemporaryDirectory() as tmp:
            memory = Path(tmp) / "memory.json"
            report = Path(tmp) / "report.json"
            result = gap.observe_pipeline(social, {}, [], memory_path=memory, report_path=report)
            self.assertEqual(result["source_family_order"][:2], ["official_direct", "official_social"])
            self.assertTrue(memory.exists())
            saved = json.loads(memory.read_text(encoding="utf-8"))
            self.assertTrue(set(saved["families"]).issubset(set(gap.SOURCE_FAMILIES)))

    def test_untrusted_memory_cannot_add_family_or_change_primary_order(self):
        memory = {
            "version": 1, "runs": 999, "cells": {},
            "families": {
                "evil_exec": {"verified": 999999, "discovered": 1},
                "community": {"verified": 20, "corroborated": 20, "discovered": 20},
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "memory.json"
            path.write_text(json.dumps(memory), encoding="utf-8")
            loaded = gap._load_memory(path)
            self.assertNotIn("evil_exec", loaded["families"])
            self.assertEqual(gap.preferred_families(loaded)[:2], ["official_direct", "official_social"])
            self.assertNotIn("evil_exec", gap.preferred_families(loaded))

    def test_channel_403_and_429_are_safety_states_not_bypass_hints(self):
        social = {"channel_status": {
            "x": {"error": "HTTP 403 Forbidden"},
            "instagram": {"error": "HTTP 429 Retry-After: 300"},
        }}
        state = gap._parse_channel_failures(social)
        self.assertTrue(state["x"]["access_control_blocked"])
        self.assertIn("자동 우회 금지", state["x"]["next_action"])
        self.assertTrue(state["instagram"]["rate_limited"])
        self.assertIn("cooldown", state["instagram"]["next_action"])

    def test_secondary_collector_stops_after_access_control_block(self):
        priority = [
            {"game": "포켓몬 카드", "region": "KR", "topic": "promo"},
            {"game": "원피스 카드", "region": "KR", "topic": "event"},
        ]
        blocked = {"ok": False, "http_status": 403, "access_control_blocked": True, "rate_limited": False}
        with mock.patch.object(gap, "_search_secondary", return_value=([], blocked)) as search:
            rows, status = gap.collect_secondary_leads(priority, max_queries=12)
        self.assertEqual(rows, [])
        self.assertTrue(status["access_control_blocked"])
        self.assertEqual(search.call_count, 1)

    def test_secondary_collector_stops_after_429_and_keeps_retry_after(self):
        priority = [{"game": "포켓몬 카드", "region": "KR", "topic": "release"}]
        limited = {
            "ok": False, "http_status": 429, "access_control_blocked": False,
            "rate_limited": True, "retry_after_seconds": 600,
        }
        with mock.patch.object(gap, "_search_secondary", return_value=([], limited)) as search:
            rows, status = gap.collect_secondary_leads(priority, max_queries=12)
        self.assertEqual(rows, [])
        self.assertTrue(status["rate_limited"])
        self.assertEqual(status["retry_after_seconds"], 600)
        self.assertEqual(search.call_count, 1)

    def test_secondary_candidate_contract_cannot_be_verified(self):
        row = {
            "game": "포켓몬 카드", "region": "KR", "topic": "event",
            "source": "https://namu.wiki/w/example", "source_tier": "C",
            "verified": True, "needs_official_confirmation": True,
        }
        self.assertEqual(gap.classify_source(row), "secondary_wiki")
        self.assertFalse(gap._verified(row))


if __name__ == "__main__":
    unittest.main()

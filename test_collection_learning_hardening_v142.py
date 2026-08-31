#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import adaptive_collection_learner
import collection_learning_hardening_v142 as hardening
import fan_social_learning
import social_event_discovery


class CollectionLearningHardeningV142Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.status = hardening.apply()

    def _learner(self, root: Path):
        return adaptive_collection_learner.AdaptiveCollectionLearner(
            memory_path=root / "adaptive.json",
            backup_path=root / "adaptive.bak.json",
            report_path=root / "adaptive.report.json",
        )

    def test_apply_is_idempotent_and_keeps_full_safety_status(self):
        first = hardening.apply()
        second = hardening.apply()
        for status in (first, second):
            self.assertEqual(142, status.get("patch"))
            self.assertIs(status.get("unique_evidence_host_counting"), True)
            self.assertIs(status.get("strict_official_social_url_match"), True)
            self.assertIs(status.get("fan_reuse_requires_corroboration_or_watch"), True)
            self.assertEqual(0.0, status.get("unverified_payload_learning_weight"))
            self.assertEqual(0.0, status.get("unverified_search_host_term_learning_weight"))

    def test_duplicate_routes_from_same_host_do_not_inflate_crosscheck(self):
        title = "포켓몬 카드 특별 프로모 행사 안내"
        base = {
            "game": "포켓몬 카드",
            "region": "KR",
            "category": "promo",
            "title": title,
            "excerpt": "동일 행사",
            "verified": False,
            "confidence": 0.70,
        }
        same_host = [
            {**base, "source": "https://a.example/one"},
            {**base, "source": "https://a.example/two"},
            {**base, "source": "https://a.example/three"},
        ]
        merged = social_event_discovery.merge_candidates(same_host)
        self.assertEqual(1, len(merged))
        self.assertEqual(1, merged[0].get("independent_source_count"))
        self.assertEqual(["a.example"], merged[0].get("evidence_hosts"))
        self.assertIs(merged[0].get("cross_checked"), False)

        mixed_hosts = same_host + [{**base, "source": "https://b.example/other"}]
        merged = social_event_discovery.merge_candidates(mixed_hosts)
        self.assertEqual(1, len(merged))
        self.assertEqual(2, merged[0].get("independent_source_count"))
        self.assertEqual({"a.example", "b.example"}, set(merged[0].get("evidence_hosts") or []))
        self.assertIs(merged[0].get("cross_checked"), True)

    def test_official_social_requires_actual_account_url_not_title_mention(self):
        with tempfile.TemporaryDirectory() as td:
            learner = self._learner(Path(td))
            self.assertTrue(learner._is_official(
                "포켓몬",
                "https://www.instagram.com/pokemon_korea_official/",
                "포켓몬 카드 공식 이벤트",
            ))
            self.assertFalse(learner._is_official(
                "포켓몬",
                "https://evil.example/post/1",
                "pokemon_korea_official 포켓몬 이벤트 모음",
            ))
            self.assertFalse(learner._is_official(
                "포켓몬",
                "https://www.instagram.com/p/not-the-account/",
                "pokemon_korea_official 재게시",
            ))

    def test_unverified_search_can_measure_query_but_cannot_teach_host_or_terms(self):
        with tempfile.TemporaryDirectory() as td:
            learner = self._learner(Path(td))
            before_terms = dict(learner.memory.get("term_stats") or {})
            result = learner.observe_search(
                "포켓몬 카드",
                "포켓몬 카드 프로모 이벤트",
                [{"title": "포켓몬 카드 프로모 이벤트 소식", "url": "https://noise.example/promo"}],
                family="web",
                region="KR",
            )
            self.assertGreaterEqual(result.get("relevant", 0), 1)
            self.assertEqual(0, result.get("official"))
            self.assertNotIn("noise.example", learner.memory.get("host_stats", {}))
            self.assertEqual(before_terms, learner.memory.get("term_stats", {}))
            self.assertGreaterEqual(len(learner.memory.get("query_stats", {})), 1)

    def test_verified_official_search_teaches_host_and_terms(self):
        with tempfile.TemporaryDirectory() as td:
            learner = self._learner(Path(td))
            result = learner.observe_search(
                "포켓몬 카드",
                "포켓몬 카드 프로모 이벤트",
                [{
                    "title": "포켓몬 카드 KANTO FESTA 프로모 이벤트",
                    "url": "https://www.instagram.com/pokemon_korea_official/",
                }],
                family="official-social",
                region="KR",
            )
            self.assertEqual(1, result.get("official"))
            host_stats = learner.memory.get("host_stats", {})
            self.assertIn("www.instagram.com", host_stats)
            self.assertGreaterEqual(int(host_stats["www.instagram.com"].get("official") or 0), 1)
            self.assertTrue(any("KANTO" in key or "FESTA" in key for key in learner.memory.get("term_stats", {})))

    def test_social_payload_learning_ignores_unverified_but_keeps_safe_evidence(self):
        rows = [
            {
                "game": "포켓몬 카드", "region": "KR", "title": "RUMOR FESTA 프로모",
                "source": "https://community.example/rumor", "verified": False,
                "source_tier": "C-community", "confidence": 0.80,
            },
            {
                "game": "포켓몬 카드", "region": "KR", "title": "OFFICIAL FESTA 프로모",
                "source": "https://www.instagram.com/pokemon_korea_official/",
                "verified": True, "official_account_verified": True, "confidence": 0.99,
            },
            {
                "game": "원피스 카드", "region": "KR", "title": "CROSS FESTA 프로모",
                "source": "https://partner-a.example/event", "verified": False,
                "cross_checked": True, "independent_source_count": 2, "confidence": 0.85,
                "source_tier": "B-crosscheck",
            },
        ]
        with tempfile.TemporaryDirectory() as td:
            learner = self._learner(Path(td))
            learned = learner.learn_from_payload({"items": rows}, origin="social")
            self.assertEqual(2, learned)
            hosts = learner.memory.get("host_stats", {})
            self.assertNotIn("community.example", hosts)
            self.assertIn("www.instagram.com", hosts)
            self.assertIn("partner-a.example", hosts)
            safety = learner.memory.get("channel_stats", {}).get("v142_learning_safety", {})
            self.assertGreaterEqual(int(safety.get("ignored_unverified_payload_rows") or 0), 1)

    def test_old_unverified_host_and_term_memory_is_scrubbed_on_load(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            memory = root / "adaptive.json"
            memory.write_text(json.dumps({
                "version": 1,
                "query_stats": {},
                "term_stats": {
                    "포켓몬|KR|rumor": {"score": 9, "official": 0, "cross_checked": 0},
                    "포켓몬|KR|official": {"score": 4, "official": 1, "cross_checked": 0},
                    "포켓몬|KR|cross": {"score": 4, "official": 0, "cross_checked": 1},
                },
                "host_stats": {
                    "noise.example": {"score": 9, "official": 0, "cross_checked": 0},
                    "official.example": {"score": 4, "official": 1, "cross_checked": 0},
                    "cross.example": {"score": 4, "official": 0, "cross_checked": 1},
                },
                "channel_stats": {}, "feedback_seen": [], "payload_seen": [],
                "totals": {"searches": 0, "results": 0, "relevant": 0, "official": 0, "errors": 0},
            }, ensure_ascii=False), encoding="utf-8")
            learner = adaptive_collection_learner.AdaptiveCollectionLearner(
                memory_path=memory,
                backup_path=root / "adaptive.bak.json",
                report_path=root / "report.json",
            )
            self.assertNotIn("noise.example", learner.memory.get("host_stats", {}))
            self.assertIn("official.example", learner.memory.get("host_stats", {}))
            self.assertIn("cross.example", learner.memory.get("host_stats", {}))
            self.assertNotIn("포켓몬|KR|rumor", learner.memory.get("term_stats", {}))
            self.assertIn("포켓몬|KR|official", learner.memory.get("term_stats", {}))
            self.assertIn("포켓몬|KR|cross", learner.memory.get("term_stats", {}))

    def test_fan_account_reuse_requires_corroboration_or_known_watch(self):
        with tempfile.TemporaryDirectory() as td:
            learner = fan_social_learning.FanSocialLearner(memory_path=Path(td) / "fan.json")
            learner.data["sources"] = {
                "instagram:unknown": {
                    "author": "unknown", "game": "포켓몬 카드", "region": "KR",
                    "discovered": 2, "selected": 2, "corroborated": 0, "known_watch_account": False,
                },
                "instagram:corroborated": {
                    "author": "corroborated", "game": "포켓몬 카드", "region": "KR",
                    "discovered": 2, "selected": 1, "corroborated": 1, "known_watch_account": False,
                },
                "instagram:known": {
                    "author": "known", "game": "포켓몬 카드", "region": "KR",
                    "discovered": 2, "selected": 1, "corroborated": 0, "known_watch_account": True,
                },
            }
            preferred = learner.preferred_authors("포켓몬 카드", "KR", limit=6)
            self.assertNotIn("unknown", preferred)
            self.assertIn("corroborated", preferred)
            self.assertIn("known", preferred)


if __name__ == "__main__":
    unittest.main()

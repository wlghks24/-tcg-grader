#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from adaptive_collection_learner import AdaptiveCollectionLearner
from multi_channel_agent import MultiChannelCollector


class AdaptiveCollectionLearnerTests(unittest.TestCase):
    def make_learner(self, root: Path) -> AdaptiveCollectionLearner:
        return AdaptiveCollectionLearner(
            memory_path=root / "memory.json",
            backup_path=root / "memory.json.bak",
            report_path=root / "report.json",
        )

    def test_query_plan_keeps_three_regions_and_social_exploration(self):
        with tempfile.TemporaryDirectory() as td:
            learner = self.make_learner(Path(td))
            plan = learner.plan_queries("나루토", max_queries=8)
            regions = {row["region"] for row in plan if row["family"] == "regional"}
            self.assertEqual(regions, {"KR", "JP", "US"})
            self.assertTrue(any(row["family"].startswith("social:") for row in plan))
            self.assertTrue(any(row["family"] in {"exploration", "official-site"} for row in plan))

    def test_verified_candidate_teaches_future_query_vocabulary_without_changing_trust_policy(self):
        with tempfile.TemporaryDirectory() as td:
            learner = self.make_learner(Path(td))
            payload = {
                "items": [
                    {
                        "game": "나루토 카드",
                        "region": "US",
                        "title": "NARUTO Yankees Chakra Card Night",
                        "source": "https://naruto-official.com/en/news/example",
                        "excerpt": "Yankees stadium collaboration limited Chakra Card",
                        "verified": True,
                        "official_domain_match": True,
                    }
                ]
            }
            self.assertEqual(learner.learn_from_payload(payload, origin="test"), 1)
            plan = learner.plan_queries("나루토", max_queries=8)
            joined = "\n".join(row["query"] for row in plan)
            self.assertTrue(any(term in joined for term in ("Yankees", "Chakra", "stadium", "Night")))
            report = learner.report()
            learned_terms = {row["term"] for row in report["top_terms"]}
            self.assertTrue({"Yankees", "Chakra"}.intersection(learned_terms))
            self.assertGreaterEqual(report["learned_terms"], 1)
            self.assertTrue(any(row["host"] == "naruto-official.com" for row in report["top_hosts"]))

    def test_repeated_payload_is_idempotent_but_verified_promotion_relearns(self):
        with tempfile.TemporaryDirectory() as td:
            learner = self.make_learner(Path(td))
            row = {
                "id": "event-1", "game": "원피스", "region": "KR",
                "title": "원피스 야구장 한정 프로모카드",
                "source": "https://example.com/event-1",
            }
            self.assertEqual(learner.learn_from_payload({"items": [row]}, origin="events"), 1)
            self.assertEqual(learner.learn_from_payload({"items": [dict(row)]}, origin="events"), 0)
            promoted = dict(row, verified=True, official_domain_match=True)
            self.assertEqual(learner.learn_from_payload({"items": [promoted]}, origin="events"), 1)
            learner.save()
            reloaded = self.make_learner(Path(td))
            self.assertEqual(reloaded.learn_from_payload({"items": [promoted]}, origin="events"), 0)

    def test_search_observation_scores_each_result_once(self):
        with tempfile.TemporaryDirectory() as td:
            learner = self.make_learner(Path(td))
            rows = [
                {"title": f"Pokemon official event promo {index}", "url": f"https://pokemon.com/event/{index}"}
                for index in range(50)
            ]
            with patch.object(learner, "_result_features", wraps=learner._result_features) as features:
                learner.observe_search("포켓몬", "pokemon event promo", rows)
            self.assertEqual(features.call_count, len(rows))

    def test_search_observation_rewards_relevant_official_hits_and_persists(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            learner = self.make_learner(root)
            rows = [
                {
                    "title": "NARUTO CARD GAME official tournament promo card event",
                    "url": "https://www.naruto-cardgame.com/en/news/sample.php",
                },
                {
                    "title": "unrelated wallpaper download",
                    "url": "https://example.com/wallpaper",
                },
            ]
            result = learner.observe_search(
                "나루토",
                "NARUTO CARD GAME event promo card",
                rows,
                family="official-site",
                region="US",
            )
            self.assertGreaterEqual(result["relevant"], 1)
            self.assertGreaterEqual(result["official"], 1)
            ranked = learner.rank_results("나루토", rows, limit=5)
            self.assertEqual(ranked[0]["url"], "https://www.naruto-cardgame.com/en/news/sample.php")
            learner.save()
            reloaded = self.make_learner(root)
            self.assertGreaterEqual(reloaded.memory["totals"]["official"], 1)
            self.assertTrue((root / "report.json").exists())

    def test_feedback_can_teach_missed_event_and_penalize_false_positive(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            learner = self.make_learner(root)
            feedback = root / "feedback.json"
            feedback.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "miss-1",
                                "game": "포켓몬 카드",
                                "region": "KR",
                                "title": "야구 브랜드데이 한정 프로모카드",
                                "source": "https://example.com/event",
                                "verdict": "missed",
                                "cross_checked": True,
                            },
                            {
                                "id": "bad-1",
                                "game": "포켓몬 카드",
                                "region": "KR",
                                "title": "배경화면 팬아트",
                                "source": "https://example.com/fanart",
                                "verdict": "false_positive",
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            self.assertEqual(learner.learn_feedback_file(feedback), 2)
            self.assertEqual(learner.learn_feedback_file(feedback), 0)
            plan = learner.plan_queries("포켓몬", max_queries=8)
            joined = "\n".join(row["query"] for row in plan)
            self.assertTrue("야구" in joined or "브랜드데이" in joined)

    def test_corrupt_primary_memory_recovers_from_backup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            primary = root / "memory.json"
            backup = root / "memory.json.bak"
            primary.write_text("{broken", encoding="utf-8")
            backup.write_text(
                json.dumps({
                    "version": 2,
                    "query_stats": {},
                    "term_stats": {},
                    "host_stats": {},
                    "channel_stats": {},
                    "totals": {"searches": 7},
                }),
                encoding="utf-8",
            )
            learner = self.make_learner(root)
            self.assertEqual(learner.memory["totals"]["searches"], 7)

    def test_web_collector_routes_mocked_results_through_learning_and_ranking(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            learner = self.make_learner(root)
            collector = MultiChannelCollector(learner=learner)
            fake_rows = [
                {
                    "title": "NARUTO CARD GAME New York event promo card",
                    "url": "https://www.naruto-cardgame.com/en/news/mock.php",
                    "verified": False,
                    "search_provider": "bing_rss",
                },
                {
                    "title": "NARUTO wallpaper download",
                    "url": "https://example.com/wallpaper",
                    "verified": False,
                    "search_provider": "google_news",
                },
            ]
            with patch.object(collector, "_search_once", return_value=(fake_rows, [], 3)):
                result = collector.search_web("나루토", limit=5)
            self.assertTrue(result["ok"])
            self.assertGreaterEqual(result["query_count"], 3)
            self.assertEqual(result["results"][0]["url"], "https://www.naruto-cardgame.com/en/news/mock.php")
            self.assertTrue(result["results"][0]["official_hint"])
            self.assertGreater(learner.memory["totals"]["searches"], 0)
            self.assertTrue((root / "memory.json").exists())

    def test_duckduckgo_redirect_decoder_recovers_real_https_target(self):
        target = "https://www.naruto-cardgame.com/en/news/test.php"
        encoded = "https://html.duckduckgo.com/l/?uddg=" + __import__("urllib.parse", fromlist=["quote"]).quote(target, safe="")
        self.assertEqual(MultiChannelCollector._decode_result_url(encoded), target)

    def test_empty_successful_search_is_not_counted_as_hard_failure(self):
        with tempfile.TemporaryDirectory() as td:
            learner = self.make_learner(Path(td))
            collector = MultiChannelCollector(learner=learner)
            with patch.object(collector, "_search_once", return_value=([], [], 3)):
                result = collector.search_web("포켓몬", limit=5)
            self.assertTrue(result["ok"])
            self.assertTrue(result["empty"])
            self.assertEqual(result["collection_errors"], [])
            self.assertEqual(result["empty_query_count"], result["query_count"])

    def test_relaxed_query_uses_or_terms_and_preserves_social_site(self):
        with tempfile.TemporaryDirectory() as td:
            learner = self.make_learner(Path(td))
            collector = MultiChannelCollector(learner=learner)
            query = collector._relaxed_query(
                "원피스", "KR", "social:x.com",
                "원피스 카드 행사 이벤트 프로모 콜라보 출시 site:x.com",
            )
            self.assertIn(" OR ", query)
            self.assertIn("site:x.com", query)
            self.assertIn("원피스", query)

    def test_round_robin_merge_prevents_bing_from_occupying_every_slot(self):
        providers = {
            "duckduckgo": [],
            "bing_rss": [
                {"title": f"Bing {i}", "url": f"https://bing.example/{i}", "search_provider": "bing_rss"}
                for i in range(8)
            ],
            "google_news": [
                {"title": f"Google {i}", "url": f"https://google.example/{i}", "search_provider": "google_news"}
                for i in range(8)
            ],
        }
        merged = MultiChannelCollector._round_robin_merge(providers, 8)
        provider_names = [row["search_provider"] for row in merged]
        self.assertEqual(len(merged), 8)
        self.assertIn("bing_rss", provider_names)
        self.assertIn("google_news", provider_names)
        self.assertLess(provider_names.count("bing_rss"), 8)
        self.assertLess(provider_names.count("google_news"), 8)

    def test_final_diversity_survives_relevance_ranking(self):
        ranked = [
            {
                "title": f"Pokemon event Bing {i}",
                "url": f"https://bing.example/event/{i}",
                "search_provider": "bing_rss",
                "relevance_score": 5.0 - i * 0.05,
                "official_hint": False,
            }
            for i in range(8)
        ]
        ranked += [
            {
                "title": "Pokemon official event Google",
                "url": "https://google.example/event/1",
                "search_provider": "google_news",
                "relevance_score": 3.8,
                "official_hint": False,
            },
            {
                "title": "Pokemon promo DuckDuckGo",
                "url": "https://ddg.example/event/1",
                "search_provider": "duckduckgo",
                "relevance_score": 3.6,
                "official_hint": False,
            },
        ]
        mixed = MultiChannelCollector._diversify_ranked(ranked, 8)
        providers = {row["search_provider"] for row in mixed}
        self.assertIn("bing_rss", providers)
        self.assertIn("google_news", providers)
        self.assertIn("duckduckgo", providers)

    def test_google_news_query_is_region_specific_and_compact(self):
        with tempfile.TemporaryDirectory() as td:
            collector = MultiChannelCollector(learner=self.make_learner(Path(td)))
            kr = collector._compact_news_query("포켓몬 카드 행사 이벤트 프로모 출시", "KR")
            jp = collector._compact_news_query("ポケモンカード イベント プロモ 発売", "JP")
            us = collector._compact_news_query("Pokemon TCG event promo release", "US")
            self.assertIn("when:60d", kr)
            self.assertIn(" OR ", kr)
            self.assertIn("ポケモンカード", jp)
            self.assertIn("Pokemon TCG", us)
            self.assertEqual(collector.GOOGLE_LOCALE["JP"]["ceid"], "JP:ja")
            self.assertEqual(collector.GOOGLE_LOCALE["US"]["ceid"], "US:en")

    def test_duckduckgo_lite_parser_accepts_external_result_links(self):
        with tempfile.TemporaryDirectory() as td:
            collector = MultiChannelCollector(learner=self.make_learner(Path(td)))
            target = "https://www.naruto-cardgame.com/en/news/test.php"
            encoded = __import__("urllib.parse", fromlist=["quote"]).quote(target, safe="")
            page = f'<html><a rel="nofollow" href="https://lite.duckduckgo.com/l/?uddg={encoded}">NARUTO CARD GAME event</a></html>'
            rows = collector._parse_ddg_lite(page, 5)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["url"], target)
            self.assertEqual(rows[0]["search_provider"], "duckduckgo")


if __name__ == "__main__":
    unittest.main()

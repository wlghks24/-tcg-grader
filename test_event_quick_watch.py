#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import event_collection_hardening_v141 as hardening
import event_gap_learning
import event_priority_watch
import event_quick_watch
import social_event_discovery


class BreakingEventWatchTests(unittest.TestCase):
    def test_pokemon_korea_instagram_is_trusted_official_source(self):
        registry = json.loads(Path("social_source_registry.json").read_text(encoding="utf-8"))
        matches = [
            row for row in registry.get("accounts", [])
            if row.get("platform") == "instagram"
            and row.get("username") == "pokemon_korea_official"
            and row.get("game") == "포켓몬 카드"
            and row.get("region") == "KR"
        ]
        self.assertEqual(1, len(matches))
        self.assertIs(matches[0].get("trusted"), True)
        self.assertIs(matches[0].get("manual"), True)
        self.assertFalse(any(
            row.get("username") == "pokemon_korea_official"
            for row in registry.get("watch_accounts", [])
        ))

    def test_quick_watch_default_interval_is_hourly(self):
        self.assertEqual(3600, event_quick_watch.DEFAULT_INTERVAL_SECONDS)
        self.assertLessEqual(event_quick_watch.DEFAULT_START_DELAY_SECONDS, 600)

    def test_priority_watch_is_lightweight_30_minute_layer(self):
        self.assertEqual(1800, event_priority_watch.DEFAULT_INTERVAL_SECONDS)
        self.assertEqual(180, event_priority_watch.DEFAULT_START_DELAY_SECONDS)
        self.assertLess(event_priority_watch.DEFAULT_INTERVAL_SECONDS, event_quick_watch.DEFAULT_INTERVAL_SECONDS)

    def test_watchers_use_v142_collection_learning_guard(self):
        self.assertEqual(142, event_priority_watch.hardening.PATCH_ID)
        self.assertEqual(142, event_quick_watch.hardening.PATCH_ID)
        self.assertIs(event_priority_watch.hardening.focused_official_social_search, hardening.focused_official_social_search)

    def test_v141_vocabulary_is_preserved_under_v142_runtime(self):
        status = hardening.apply()
        self.assertEqual(141, status["patch"])
        self.assertEqual("movie", social_event_discovery._category("슈퍼 티저 비주얼과 예고편 공개"))
        self.assertIn("티저", social_event_discovery.EVENT_TERMS["ko"])
        self.assertIn("trailer", social_event_discovery.EVENT_TERMS["en"].lower())
        self.assertIn("선착순", social_event_discovery.EVENT_TERMS["ko"])
        self.assertIn("한정판", social_event_discovery.EVENT_TERMS["ko"])

    def test_v141_targets_trusted_official_accounts(self):
        registry = json.loads(Path("social_source_registry.json").read_text(encoding="utf-8"))
        rows = hardening._trusted_accounts(registry, "포켓몬 카드", "KR")
        names = {str(row.get("username") or "").lower() for row in rows}
        self.assertIn("pokemon_korea_official", names)
        self.assertNotIn("poke_vending_machine", names)

    def test_v141_detects_out_of_scope_card_and_limited_giveaways(self):
        hardening.apply()
        examples = (
            "포켓몬 카드 구매 시 한정 프로모 카드 1장 선착순 증정",
            "원피스 콜라보 한정판 카드를 방문 고객에게 무료 배포",
            "나루토 프로모션 팩을 참가자에게 지급합니다",
            "限定プロモカードを来場者に無料配布",
            "Receive an exclusive promo card while supplies last",
        )
        for text in examples:
            with self.subTest(text=text):
                self.assertTrue(hardening.reward_signal(text))
        self.assertFalse(hardening.reward_signal("포켓몬 신작 애니메이션 영상 공개"))
        self.assertFalse(hardening.reward_signal("원피스 한정판 카드 일반 판매 시작"))
        self.assertEqual("promo", social_event_discovery._category("프로모 카드 선착순 증정"))

    def test_v141_reward_annotation_preserves_unverified_candidate_status(self):
        row = {
            "game": "원피스 카드",
            "region": "KR",
            "category": "promo",
            "title": "콜라보 한정 카드를 선착순 증정",
            "excerpt": "매장 방문 고객에게 한정 프로모 카드 무료 증정",
            "source": "https://www.instagram.com/community_example/",
            "source_kind": "instagram_public_search",
            "source_tier": "C-community",
            "verified": False,
            "official_account_verified": False,
            "confidence": 0.52,
        }
        marked = hardening._annotate_reward_row(row)
        self.assertIs(marked.get("reward_watch"), True)
        self.assertIs(marked.get("must_show_candidate"), True)
        self.assertEqual("tcg_reward_or_giveaway", marked.get("collection_scope_override"))
        self.assertIs(marked.get("verified"), False)
        self.assertIs(marked.get("official_account_verified"), False)
        self.assertGreaterEqual(float(marked.get("confidence") or 0), 0.64)

    def test_v142_verified_reward_learning_is_guarded_and_weighted(self):
        official = {
            "game": "포켓몬 카드",
            "region": "KR",
            "category": "promo",
            "title": "KANTO FESTA 한정 프로모 카드 선착순 증정",
            "excerpt": "행사 참여자에게 스페셜 카드 무료 배포",
            "source": "https://www.instagram.com/pokemon_korea_official/",
            "source_label": "공식 SNS 카드/한정품 증정 탐색",
            "reward_watch": True,
            "verified": True,
            "official_account_verified": True,
            "official_domain_match": False,
            "cross_checked": False,
            "confidence": 0.99,
        }
        cross = {
            "game": "원피스 카드",
            "region": "KR",
            "category": "promo",
            "title": "GRAND HARBOR 한정 프로모 카드 무료 배포",
            "excerpt": "독립된 두 공식 발표에서 행사 특전 확인",
            "source": "https://partner-a.example/event",
            "source_label": "교차확인 증정정보",
            "reward_watch": True,
            "verified": False,
            "official_account_verified": False,
            "official_domain_match": False,
            "cross_checked": True,
            "independent_source_count": 2,
            "confidence": 0.90,
        }
        unverified = {
            "game": "나루토 카드",
            "region": "KR",
            "category": "promo",
            "title": "RUMOR FESTA 한정 카드 무료 증정",
            "excerpt": "커뮤니티 제보",
            "source": "https://www.instagram.com/community_example/",
            "source_label": "커뮤니티 후보",
            "reward_watch": True,
            "verified": False,
            "official_account_verified": False,
            "cross_checked": False,
            "confidence": 0.68,
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence = root / "social_event_candidates.json"
            memory = root / "event_gap_learning.json"
            evidence.write_text(json.dumps({"items": [official, cross, unverified]}, ensure_ascii=False), encoding="utf-8")
            learner = event_gap_learning.EventGapLearner(memory_path=memory)
            learned = event_priority_watch.hardening.learn_verified_reward_candidates(learner, evidence)
            self.assertEqual(2, learned)
            official_stats = [
                stat for key, stat in learner.data.get("terms", {}).items()
                if "KANTO FESTA" in key
            ]
            cross_stats = [
                stat for key, stat in learner.data.get("terms", {}).items()
                if "GRAND HARBOR" in key
            ]
            self.assertTrue(official_stats)
            self.assertTrue(cross_stats)
            self.assertEqual(1.35, official_stats[0].get("last_learning_weight"))
            self.assertEqual(0.90, cross_stats[0].get("last_learning_weight"))
            self.assertFalse(any("RUMOR FESTA" in key for key in learner.data.get("terms", {})))

    def test_v141_learning_capacity_is_bounded_but_expanded(self):
        hardening.apply()
        self.assertGreaterEqual(event_gap_learning.MAX_TERMS, 900)
        self.assertGreaterEqual(event_gap_learning.MAX_SEEN, 800)
        self.assertLessEqual(event_gap_learning.MAX_TERMS, 5000)
        self.assertLessEqual(event_gap_learning.MAX_SEEN, 5000)

    def test_v141_broadens_candidate_cap_without_overriding_explicit_environment(self):
        hardening.apply()
        self.assertGreaterEqual(social_event_discovery.MAX_ITEMS, 180)

    def test_repository_keeps_current_wild_card_gap_as_manual_evidence(self):
        payload = json.loads(Path("manual_event_evidence.json").read_text(encoding="utf-8"))
        matches = [
            row for row in payload.get("items", [])
            if row.get("game") == "포켓몬 카드"
            and row.get("region") == "KR"
            and row.get("category") == "movie"
            and "와일드카드" in str(row.get("title") or "")
        ]
        self.assertEqual(1, len(matches))
        self.assertIs(matches[0].get("manual_evidence"), True)
        self.assertIs(matches[0].get("official_account_verified"), True)
        self.assertIn("wild card", [str(x).lower() for x in matches[0].get("dedupe_terms", [])])

    def test_manual_official_evidence_teaches_future_search_terms_only_when_verified(self):
        good = {
            "game": "포켓몬 카드",
            "region": "KR",
            "category": "movie",
            "title": "THE MOVIE 포켓몬 와일드카드 슈퍼 티저 비주얼",
            "excerpt": "CloverWorks 장편 애니메이션 티저 예고 공개",
            "source": "https://www.instagram.com/pokemon_korea_official/",
            "manual_evidence": True,
            "official_account_verified": True,
            "verified": True,
        }
        bad = dict(good)
        bad["title"] = "미검증 커뮤니티 루머"
        bad["source"] = "https://www.instagram.com/community_example/"
        bad["official_account_verified"] = False
        bad["verified"] = False
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence = root / "manual_event_evidence.json"
            memory = root / "event_gap_learning.json"
            evidence.write_text(json.dumps({"items": [good, bad]}, ensure_ascii=False), encoding="utf-8")
            learner = event_gap_learning.EventGapLearner(memory_path=memory)
            learned = hardening.base.base.learn_manual_official_evidence(learner, evidence)
            self.assertEqual(1, learned)
            terms = learner.terms_for("포켓몬 카드", "KR", "movie", limit=8)
            self.assertTrue(any(term in terms for term in ("와일드카드", "CloverWorks", "티저")))
            self.assertFalse(any("루머" in key for key in learner.data.get("terms", {})))

    def test_manual_movie_evidence_is_merged_and_later_deduped(self):
        seed = {
            "game": "포켓몬 카드",
            "region": "KR",
            "category": "movie",
            "title": "THE MOVIE 「포켓몬: 와일드카드」 · 2027년 극장 개봉 발표",
            "dedupe_terms": ["와일드카드", "wild card"],
            "source": "https://www.instagram.com/pokemon_korea_official/",
            "author": "pokemon_korea_official",
            "manual_evidence": True,
            "official_account_verified": True,
            "verified": True,
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence = root / "manual_event_evidence.json"
            output = root / "social_event_candidates.json"
            evidence.write_text(json.dumps({"items": [seed]}, ensure_ascii=False), encoding="utf-8")
            base = {
                "items": [],
                "fresh_collection_ok": True,
                "degraded": False,
                "collection_errors": [],
            }
            with mock.patch.object(event_quick_watch, "MANUAL_EVIDENCE", evidence), \
                 mock.patch.object(social_event_discovery, "OUT", output):
                merged, added = event_quick_watch._merge_manual_evidence(base)
                self.assertEqual(1, added)
                self.assertEqual("movie", merged["items"][0]["category"])
                self.assertEqual(1, merged["manual_evidence_count"])
                self.assertTrue(output.exists())

                discovered = dict(seed)
                discovered["title"] = "Pokémon Wild Card movie announced for 2027"
                discovered["manual_evidence"] = False
                discovered["source"] = "https://example.com/official-crosscheck"
                merged_again, added_again = event_quick_watch._merge_manual_evidence({
                    "items": [discovered],
                    "fresh_collection_ok": True,
                    "degraded": False,
                    "collection_errors": [],
                })
                self.assertEqual(0, added_again)
                self.assertEqual(1, len(merged_again["items"]))


if __name__ == "__main__":
    unittest.main()

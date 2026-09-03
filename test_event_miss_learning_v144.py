#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import collection_learning_hardening_v144 as hardening
import event_gap_learning
import event_source_overlay_v144 as source_overlay
import social_event_discovery


source_overlay.apply()
hardening.apply()


class EventMissLearningV144Tests(unittest.TestCase):
    def _registry(self):
        raw = json.loads(Path("social_source_registry.json").read_text(encoding="utf-8"))
        return source_overlay.merge_registry(raw)

    def test_official_onepiece_and_jump_jp_sources_are_added_without_trusting_community(self):
        registry = self._registry()
        official = {
            (str(row.get("username") or "").lower(), row.get("region"))
            for row in registry.get("accounts", [])
            if row.get("game") == "원피스 카드" and row.get("trusted") is True
        }
        self.assertIn(("eiichiro_staff", "JP"), official)
        self.assertIn(("jump_henshubu", "JP"), official)

        watch = next(
            row for row in registry.get("watch_accounts", [])
            if row.get("username") == "onepiececard_news"
        )
        self.assertIs(watch.get("trusted"), False)
        self.assertEqual(["KR", "JP", "US"], watch.get("content_regions"))

    def test_official_social_match_requires_actual_profile_url_not_title_mention(self):
        registry = self._registry()
        fake = hardening._strict_official_social_match(
            registry,
            "https://x.com/community_example/status/123",
            "Eiichiro_Staff official announcement repost",
            "원피스 카드",
            "JP",
        )
        real = hardening._strict_official_social_match(
            registry,
            "https://x.com/Eiichiro_Staff/status/123",
            "ONE PIECE announcement",
            "원피스 카드",
            "JP",
        )
        self.assertEqual((False, None), fake)
        self.assertEqual((True, "Eiichiro_Staff"), real)

    def test_verified_manual_miss_teaches_terms_and_region_hints_but_rumor_does_not(self):
        good = {
            "game": "원피스 카드",
            "region": "JP",
            "category": "collaboration",
            "title": "ONE PIECE Nike 콜라보 프로모 카드 응모자 전원 서비스",
            "excerpt": "Dr. B's RESEARCH LAB 대상상품 구매와 週刊少年ジャンプ 定期購読 응모 안내",
            "location": "東京 原宿",
            "source": "https://x.com/Eiichiro_Staff",
            "manual_evidence": True,
            "verified": True,
            "official_account_verified": True,
            "learning_terms": ["Nike", "Dr. B's RESEARCH LAB", "応募者全員サービス", "定期購読"],
            "region_anchors": ["東京", "Tokyo", "原宿", "Harajuku", "集英社", "週刊少年ジャンプ"],
            "recovery_case_id": "verified-nike-test",
        }
        bad = {
            "game": "원피스 카드",
            "region": "JP",
            "category": "collaboration",
            "title": "RUMOR ONLY SECRET COLLAB",
            "excerpt": "커뮤니티 루머",
            "source": "https://www.instagram.com/community_example/",
            "manual_evidence": True,
            "verified": False,
            "official_account_verified": False,
            "learning_terms": ["RUMOR ONLY"],
            "region_anchors": ["RUMORLAND"],
            "recovery_case_id": "unverified-rumor-test",
        }
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence = root / "manual_event_evidence.json"
            memory = root / "event_gap_learning.json"
            evidence.write_text(json.dumps({"items": [good, bad]}, ensure_ascii=False), encoding="utf-8")
            learner = event_gap_learning.EventGapLearner(memory_path=memory)
            learned = learner.learn_verified_evidence_file(evidence)
            self.assertEqual(1, learned)
            learned_terms = " ".join(learner.top_terms_for_region("원피스 카드", "JP", limit=16))
            self.assertIn("Nike", learned_terms)
            self.assertIn("応募者全員サービス", learned_terms)
            self.assertNotIn("RUMOR ONLY", learned_terms)
            self.assertFalse(any("RUMORLAND" in key for key in learner.data.get("region_hints", {})))

            region, confidence, signals = learner.infer_region(
                "원피스 카드",
                "한국어 게시물이지만 나이키 도쿄 하라주쿠 행사와 슈에이샤 주간소년점프 응모를 안내",
                "KR",
            )
            self.assertEqual("JP", region)
            self.assertGreaterEqual(confidence, 0.65)
            self.assertTrue(signals)

    def test_cross_region_watch_query_uses_multilingual_and_learned_verified_terms(self):
        registry = self._registry()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence = root / "manual.json"
            memory = root / "memory.json"
            evidence.write_text(json.dumps({
                "items": [{
                    "game": "원피스 카드",
                    "region": "JP",
                    "category": "promo",
                    "title": "Nike promo",
                    "source": "https://x.com/Eiichiro_Staff",
                    "manual_evidence": True,
                    "verified": True,
                    "official_account_verified": True,
                    "learning_terms": ["Nike", "応募者全員サービス"],
                    "region_anchors": ["東京"],
                    "recovery_case_id": "query-learning-test",
                }]
            }, ensure_ascii=False), encoding="utf-8")
            learner = event_gap_learning.EventGapLearner(memory_path=memory)
            self.assertEqual(1, learner.learn_verified_evidence_file(evidence))
            query = hardening.build_public_social_query(
                "원피스 카드", "JP", registry, fan_learner=None, gap_learner=learner
            )
            self.assertIn("onepiececard_news", query)
            self.assertIn("응모", query)
            self.assertIn("応募", query)
            self.assertIn("Nike", query)
            self.assertIn("site:instagram.com", query)

    def test_region_correction_keeps_community_candidate_unverified(self):
        registry = self._registry()
        row = {
            "game": "원피스 카드",
            "region": "KR",
            "category": "collaboration",
            "title": "나이키 도쿄 하라주쿠 원피스 카드 콜라보 프로모 배포 · 슈에이샤 주간소년점프 응모",
            "excerpt": "일본 Tokyo Dr. B's RESEARCH LAB 대상상품 구매 안내",
            "source": "https://www.instagram.com/onepiececard_news/",
            "source_kind": "instagram_public_search",
            "verified": False,
            "official_account_verified": False,
            "confidence": 0.57,
        }
        result = social_event_discovery._annotate_social_rows([row], registry)[0]
        self.assertEqual("JP", result.get("region"))
        self.assertEqual("KR", result.get("region_original"))
        self.assertIs(result.get("region_inferred_from_content"), True)
        self.assertIs(result.get("fan_candidate"), True)
        self.assertIs(result.get("fan_account_known"), True)
        self.assertIs(result.get("verified"), False)
        self.assertIs(result.get("official_account_verified"), False)
        self.assertEqual("none", result.get("region_inference_trust_effect"))

    def test_repository_keeps_current_nike_onepiece_miss_as_verified_recovery_case(self):
        payload = json.loads(Path("manual_event_evidence.json").read_text(encoding="utf-8"))
        matches = [
            row for row in payload.get("items", [])
            if row.get("recovery_case_id") == "onepiece-jp-nike-promo-2026-09-03"
        ]
        self.assertEqual(1, len(matches))
        row = matches[0]
        self.assertEqual("원피스 카드", row.get("game"))
        self.assertEqual("JP", row.get("region"))
        self.assertIs(row.get("manual_evidence"), True)
        self.assertIs(row.get("verified"), True)
        self.assertIs(row.get("official_account_verified"), True)
        self.assertIs(row.get("reward_watch"), True)
        self.assertIn("応募者全員サービス", row.get("learning_terms", []))
        self.assertIn("週刊少年ジャンプ", row.get("region_anchors", []))

    def test_learning_memory_is_bounded_and_never_promotes_trust(self):
        status = hardening.apply()
        self.assertEqual(144, status["patch"])
        self.assertLessEqual(event_gap_learning.MAX_TERMS, 5000)
        self.assertLessEqual(event_gap_learning.MAX_REGION_HINTS, 5000)
        self.assertLessEqual(event_gap_learning.MAX_RECOVERIES, 1000)
        self.assertEqual(0.0, status["unverified_learning_weight"])
        self.assertIs(status["trust_auto_promotion"], False)


if __name__ == "__main__":
    unittest.main()

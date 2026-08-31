#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

import adaptive_collection_learner
import collection_learning_hardening_v144 as v144
import event_source_expansion_v145 as v145
import fan_social_learning
import manual_collection_mode
import manual_official_verified_integration_v154 as official_integration
import multi_channel_agent
import multi_route_event_discovery as routes
import social_event_discovery as social


class RuntimeOverlayCompositionV347Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        v144.apply()
        v145.apply()
        manual_collection_mode.apply()

    def test_malformed_fan_limit_stays_bounded_after_learning_overlay(self):
        with tempfile.TemporaryDirectory() as td:
            learner = fan_social_learning.FanSocialLearner(memory_path=Path(td) / "fan.json")
            learner.data["sources"]["x:safe"] = {
                "author": "safe",
                "game": "포켓몬 카드",
                "region": "KR",
                "selected": 1,
                "known_watch_account": True,
            }
            self.assertEqual(learner.preferred_authors("포켓몬 카드", "KR", "invalid"), ["safe"])

    def test_partial_provider_error_never_adds_negative_neural_label_after_overlay(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            learner = adaptive_collection_learner.AdaptiveCollectionLearner(
                memory_path=root / "memory.json",
                backup_path=root / "memory.json.bak",
                report_path=root / "report.json",
            )
            learner.neural_labels_path = root / "labels.jsonl"
            learner.neural_model_path = root / "model.json"
            collector = multi_channel_agent.MultiChannelCollector(learner=learner)
            with mock.patch.object(
                collector,
                "_search_once",
                return_value=([], ["bing_web_rss: TimeoutError"], 3, False, 3),
            ):
                result = collector.search_web("포켓몬", limit=5)
            learned = [row.get("learned", {}) for row in result.get("query_results", [])]
            self.assertTrue(learned)
            self.assertTrue(all(row.get("neural_label_added") == 0 for row in learned))
            self.assertTrue(all(row.get("neural_label_reason") == "error_observation_excluded" for row in learned))
            self.assertFalse((root / "labels.jsonl").exists())

    def test_social_overlay_uses_canonical_network_gate_and_all_discovery_hosts(self):
        captured = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self, _limit):
                return b""

        def fake_urlopen(req, **_kwargs):
            captured["url"] = req.full_url
            return Response()

        with mock.patch.object(social, "safe_urlopen", side_effect=fake_urlopen):
            rows, error = social._ddg_social_one("나루토 카드", "US", {"watch_accounts": []}, None)
        self.assertEqual(rows, [])
        self.assertIsNone(error)
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(captured["url"]).query)["q"][0]
        for host in ("tiktok.com", "twitch.tv", "facebook.com"):
            self.assertIn(f"site:{host}", query)

    def test_partner_allowlist_preserves_declared_aliases_after_rotation_build(self):
        for host in ("seoulmediacomics.com", "www.seoulmediacomics.com"):
            self.assertIn(host, routes.PARTNER_HOSTS)
            self.assertNotIn(host, routes.OFFICIAL_HOSTS)

    def test_manual_registry_runtime_method_is_exact(self):
        rows = [{"company": "BRG", "game": "pokemon", "grade": 10.0, "certification_id": "0346643"}]
        with mock.patch("graded_photo_multi_source.atomic_write_json"):
            output, _ = manual_collection_mode._registry_only_official_verify_rows(
                rows, {("BRG", "0346643"): 10.0}
            )
        self.assertEqual(output[0]["verification_method"], "persisted_manual_verified_registry")

    def test_integrated_submit_does_not_republish_current_base_acceptance(self):
        registration = {
            "registration_id": "manual-v347",
            "official_result": True,
            "official_verification_source": "user_browser_official_page",
        }
        with mock.patch.object(
            official_integration,
            "_ORIGINAL_SUBMIT",
            return_value={"accepted": True, "registration": registration},
        ), mock.patch.object(official_integration, "promote_registration") as promote:
            result = official_integration._submit_integrated({"action": "complete_manual_verification"})
        promote.assert_not_called()
        self.assertTrue(result["official_result"])
        self.assertTrue(result["official_promotion"]["already_official"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

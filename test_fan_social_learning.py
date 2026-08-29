import json
import tempfile
import unittest
from pathlib import Path

from fan_social_learning import FanSocialLearner


class FanSocialLearningTests(unittest.TestCase):
    def test_fan_sources_are_learned_as_utility_not_trust(self):
        with tempfile.TemporaryDirectory() as td:
            memory = Path(td) / "fan.json"
            learner = FanSocialLearner(memory_path=memory)
            discovered = [{
                "game": "포켓몬 카드",
                "region": "KR",
                "source": "https://x.com/cardfan/status/123",
                "source_kind": "x_public_search",
                "author": "cardfan",
                "fan_candidate": True,
                "fan_account_known": False,
                "fan_source_key": "x:cardfan",
            }]
            self.assertEqual(learner.observe_discovered(discovered), 1)
            selected = [{
                **discovered[0],
                "fan_sources": ["x:cardfan"],
                "cross_checked": True,
                "independent_source_count": 2,
            }]
            self.assertEqual(learner.observe_selected(selected), 1)
            learner.save()

            data = json.loads(memory.read_text(encoding="utf-8"))
            self.assertIn("x:cardfan", data["sources"])
            self.assertNotIn("trusted", data["sources"]["x:cardfan"])
            self.assertEqual(learner.preferred_authors("포켓몬 카드", "KR", 3), ["cardfan"])

    def test_official_rows_do_not_enter_fan_learning(self):
        with tempfile.TemporaryDirectory() as td:
            learner = FanSocialLearner(memory_path=Path(td) / "fan.json")
            official = [{
                "game": "원피스 카드", "region": "KR",
                "source": "https://x.com/official/status/1",
                "source_kind": "x", "author": "official",
                "fan_candidate": False, "official_account_verified": True,
            }]
            self.assertEqual(learner.observe_discovered(official), 0)
            self.assertEqual(learner.report()["sources"], [])


if __name__ == "__main__":
    unittest.main()

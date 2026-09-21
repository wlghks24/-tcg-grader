import json
import tempfile
import unittest
from pathlib import Path

import fan_social_learning as learning


class FanSocialLearningConcurrencyV279Tests(unittest.TestCase):
    def test_stale_learners_merge_sources_and_run_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "fan_social_learning.json"
            backup = root / "fan_social_learning.json.bak"

            first = learning.FanSocialLearner(memory, backup)
            second = learning.FanSocialLearner(memory, backup)

            first.observe_discovered([
                {
                    "fan_candidate": True,
                    "fan_source_key": "x:alpha",
                    "game": "포켓몬",
                    "region": "KR",
                    "author": "alpha",
                    "source_kind": "x_social",
                }
            ])
            first.observe_selected([
                {
                    "fan_candidate": True,
                    "fan_source_key": "x:alpha",
                    "cross_checked": True,
                }
            ])
            first.save()

            second.observe_discovered([
                {
                    "fan_candidate": True,
                    "fan_source_key": "instagram:beta",
                    "game": "원피스",
                    "region": "JP",
                    "author": "beta",
                    "source_kind": "instagram_social",
                }
            ])
            second.observe_selected([
                {
                    "fan_candidate": True,
                    "fan_source_key": "instagram:beta",
                    "independent_source_count": "NaN",
                }
            ])
            second.save()

            payload = json.loads(memory.read_text(encoding="utf-8"))
            self.assertEqual(payload["runs"], 2)
            self.assertIn("x:alpha", payload["sources"])
            self.assertIn("instagram:beta", payload["sources"])
            self.assertEqual(payload["sources"]["x:alpha"]["discovered"], 1)
            self.assertEqual(payload["sources"]["x:alpha"]["selected"], 1)
            self.assertEqual(payload["sources"]["x:alpha"]["corroborated"], 1)
            self.assertEqual(payload["sources"]["instagram:beta"]["discovered"], 1)
            self.assertEqual(payload["sources"]["instagram:beta"]["selected"], 1)
            self.assertEqual(payload["sources"]["instagram:beta"].get("corroborated", 0), 0)

            # first is stale after second.save(); only its new local delta should
            # be added, while beta remains intact.
            first.observe_discovered([
                {
                    "fan_candidate": True,
                    "fan_source_key": "x:alpha",
                    "game": "포켓몬",
                    "region": "KR",
                    "author": "alpha",
                    "source_kind": "x_social",
                }
            ])
            first.save()
            payload = json.loads(memory.read_text(encoding="utf-8"))
            self.assertEqual(payload["runs"], 2)
            self.assertEqual(payload["sources"]["x:alpha"]["discovered"], 2)
            self.assertEqual(payload["sources"]["instagram:beta"]["discovered"], 1)

    def test_negative_local_deltas_never_reduce_disk_counts(self):
        disk = {"discovered": 9, "selected": 4, "corroborated": 2}
        base = {"discovered": 7, "selected": 3, "corroborated": 2}
        local = {"discovered": 6, "selected": 2, "corroborated": 1}
        merged = learning._merge_source(base, local, disk)
        self.assertEqual(merged["discovered"], 9)
        self.assertEqual(merged["selected"], 4)
        self.assertEqual(merged["corroborated"], 2)


if __name__ == "__main__":
    unittest.main()

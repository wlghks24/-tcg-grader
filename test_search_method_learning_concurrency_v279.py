import json
import tempfile
import unittest
from pathlib import Path

import search_method_learning as learning


class SearchMethodLearningConcurrencyV279Tests(unittest.TestCase):
    def test_stale_learners_merge_cumulative_updates_without_loss(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = root / "search_method_learning.json"
            backup = root / "search_method_learning.json.bak"
            old_profile = learning.PROFILE
            learning.PROFILE = root / "search_engine_profile.json"
            try:
                first = learning.SearchMethodLearner(memory, backup)
                second = learning.SearchMethodLearner(memory, backup)

                first.start_run()
                first.observe(
                    "ddg_html",
                    responded=True,
                    result_count=2,
                    elapsed_ms=120,
                    region="KR",
                    family="official",
                )
                first.observe_selected([
                    {
                        "search_method": "ddg_html",
                        "query_region": "KR",
                        "query_family": "official",
                    }
                ])
                first.save()

                # `second` was instantiated before `first.save()`.  A naive
                # last-writer-wins save would erase the ddg observation here.
                second.start_run()
                second.observe(
                    "bing_web_rss",
                    responded=True,
                    result_count=3,
                    elapsed_ms=240,
                    region="JP",
                    family="release",
                )
                second.save()

                merged = learning.SearchMethodLearner(memory, backup)
                self.assertEqual(merged.data["totals"]["runs"], 2)
                self.assertEqual(merged.data["totals"]["attempts"], 2)
                self.assertEqual(merged.data["methods"]["ddg_html"]["attempts"], 1)
                self.assertEqual(merged.data["methods"]["ddg_html"]["selected"], 1)
                self.assertEqual(merged.data["methods"]["bing_web_rss"]["attempts"], 1)
                self.assertIn("ddg_html|KR|official", merged.data["contexts"])
                self.assertIn("bing_web_rss|JP|release", merged.data["contexts"])

                # The first learner is stale again after the second save.  Its
                # next delta must merge onto the new disk state rather than
                # double-count its earlier observation or erase bing's data.
                first.observe(
                    "ddg_html",
                    responded=False,
                    result_count=0,
                    error="timeout",
                    elapsed_ms=1000,
                    region="KR",
                    family="official",
                )
                first.save()
                payload = json.loads(memory.read_text(encoding="utf-8"))
                self.assertEqual(payload["totals"]["runs"], 2)
                self.assertEqual(payload["totals"]["attempts"], 3)
                self.assertEqual(payload["methods"]["ddg_html"]["attempts"], 2)
                self.assertEqual(payload["methods"]["bing_web_rss"]["attempts"], 1)
                self.assertEqual(payload["methods"]["ddg_html"]["timeouts"], 1)
            finally:
                learning.PROFILE = old_profile

    def test_merge_helpers_ignore_negative_counter_deltas(self):
        disk = {"attempts": 8, "results": 20, "selected": 3}
        base = {"attempts": 5, "results": 10, "selected": 2}
        local = {"attempts": 4, "results": 9, "selected": 1}
        merged = learning._merge_stat(base, local, disk)
        self.assertEqual(merged["attempts"], 8)
        self.assertEqual(merged["results"], 20)
        self.assertEqual(merged["selected"], 3)


if __name__ == "__main__":
    unittest.main()

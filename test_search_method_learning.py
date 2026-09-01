import datetime as dt
import tempfile
import unittest
from pathlib import Path

from search_method_learning import SearchMethodLearner, classify_error


class SearchMethodLearningTests(unittest.TestCase):
    def make_learner(self):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        learner = SearchMethodLearner(root / "memory.json", root / "memory.bak")
        learner._test_tmp = td
        learner.start_run()
        return learner

    def test_error_classification(self):
        self.assertEqual(classify_error("HTTP Error 429"), "rate_limited")
        self.assertEqual(classify_error("HTTP Error 403 Forbidden"), "blocked")
        self.assertEqual(classify_error("TimeoutError timed out"), "timeout")

    def test_blocked_route_cools_down_without_blacklist(self):
        learner = self.make_learner()
        learner.observe("ddg_html", responded=False, result_count=0, error="HTTP Error 403 Forbidden", elapsed_ms=100)
        report = learner.report()
        row = next(x for x in report["methods"] if x["method"] == "ddg_html")
        self.assertTrue(row["cooling_down"])
        ordered = learner.ordered_routes(["ddg_html", "bing_web_rss"], budget=2)
        self.assertIn("bing_web_rss", ordered)
        self.assertNotIn("ddg_html", ordered)
        # Recovery is possible after the cooldown/transport condition clears: a successful observation clears cooldown.
        learner.observe("ddg_html", responded=True, result_count=2, error="", elapsed_ms=80)
        row = next(x for x in learner.report()["methods"] if x["method"] == "ddg_html")
        self.assertFalse(row["cooling_down"])

    def test_fast_useful_route_ranks_above_repeated_timeout(self):
        learner = self.make_learner()
        for _ in range(4):
            learner.observe("bing_news_rss", responded=True, result_count=5, elapsed_ms=120)
            learner.observe("naver_news_html", responded=False, result_count=0, error="TimeoutError timed out", elapsed_ms=20000)
        order = learner.ordered_routes(["naver_news_html", "bing_news_rss"], budget=2)
        self.assertEqual(order[0], "bing_news_rss")

    def test_selection_is_learned_separately_from_trust(self):
        learner = self.make_learner()
        learner.observe("google_news_rss", responded=True, result_count=4, elapsed_ms=100)
        learner.observe_selected([{"search_method": "google_news_rss", "verified": False}])
        row = next(x for x in learner.report()["methods"] if x["method"] == "google_news_rss")
        self.assertEqual(row["selected"], 1)
        self.assertNotIn("verified", row)

    def test_selection_is_learned_for_region_and_query_family(self):
        learner = self.make_learner()
        learner.observe(
            "google_news_rss", responded=True, result_count=4, elapsed_ms=100,
            region="JP", family="topic:promo",
        )
        learner.observe_selected([{
            "search_method": "google_news_rss",
            "query_region": "JP",
            "query_family": "topic:promo",
            "verified": False,
        }])
        context = learner.data["contexts"]["google_news_rss|JP|topic:promo"]
        self.assertEqual(context["selected"], 1)
        report_context = next(
            row for row in learner.report()["top_contexts"]
            if row["method"] == "google_news_rss" and row["region"] == "JP"
            and row["family"] == "topic:promo"
        )
        self.assertEqual(report_context["selected"], 1)
        self.assertEqual(report_context["adoption_rate"], 0.25)
        self.assertNotIn("verified", context)

    def test_reporting_does_not_create_unused_contexts(self):
        learner = self.make_learner()
        learner.observe("bing_news_rss", responded=True, result_count=2, region="US", family="movie")
        before = set(learner.data["contexts"])
        learner.report()
        self.assertEqual(before, set(learner.data["contexts"]))


if __name__ == "__main__":
    unittest.main()

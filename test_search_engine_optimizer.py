import tempfile
import unittest
from pathlib import Path

from search_method_learning import SearchMethodLearner


class SearchEngineOptimizerTests(unittest.TestCase):
    def make_learner(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        learner = SearchMethodLearner(root / "memory.json", root / "memory.bak.json")
        learner.start_run()
        return learner

    def test_healthy_method_gets_stronger_score_than_blocked_method(self):
        learner = self.make_learner()
        for _ in range(12):
            learner.observe("healthy", responded=True, result_count=5, elapsed_ms=900, region="KR", family="event")
        learner.observe_selected([{"search_method": "healthy"}] * 8)
        for _ in range(12):
            learner.observe("blocked", responded=False, result_count=0, error="HTTP Error 403: Forbidden", elapsed_ms=200, region="KR", family="event")
        self.assertGreater(
            learner.method_score("healthy", "KR", "event"),
            learner.method_score("blocked", "KR", "event"),
        )

    def test_policy_uses_metrics_for_timeout_and_attempts(self):
        learner = self.make_learner()
        for _ in range(10):
            learner.observe("stable", responded=True, result_count=3, elapsed_ms=1200, region="JP", family="release")
        stable = learner.route_policy("stable", region="JP", family="release")
        self.assertGreaterEqual(stable["timeout_seconds"], 7)
        self.assertEqual(stable["max_attempts"], 2)

        for _ in range(8):
            learner.observe("limited", responded=False, result_count=0, error="429 Too Many Requests", elapsed_ms=100, region="JP", family="release")
        limited = learner.route_policy("limited", region="JP", family="release")
        self.assertEqual(limited["max_attempts"], 1)
        self.assertLessEqual(limited["timeout_seconds"], 15)

    def test_report_exposes_requested_cumulative_metrics(self):
        learner = self.make_learner()
        learner.observe("engine", responded=True, result_count=4, elapsed_ms=500, region="US", family="promo")
        learner.observe("engine", responded=False, result_count=0, error="timed out", elapsed_ms=10000, region="US", family="promo")
        learner.observe_selected([{"search_method": "engine"}])
        report = learner.report()
        row = next(x for x in report["methods"] if x["method"] == "engine")
        for key in (
            "attempts", "response_rate", "nonempty_rate", "adoption_rate", "results", "selected",
            "empty", "blocked", "blocked_rate", "rate_limited", "rate_limited_rate",
            "timeouts", "timeout_rate", "avg_latency_ms", "failure_streak",
            "recommended_timeout_seconds", "recommended_max_attempts",
        ):
            self.assertIn(key, row)

    def test_budget_expands_when_route_health_is_poor(self):
        learner = self.make_learner()
        names = [f"m{i}" for i in range(7)]
        for name in names:
            for _ in range(4):
                learner.observe(name, responded=False, result_count=0, error="timeout", elapsed_ms=5000)
        self.assertEqual(learner.recommended_budget(names, is_android=False), 7)
        self.assertEqual(learner.recommended_budget(names, is_android=True), 5)

    def test_context_adoption_selects_different_best_routes_by_region(self):
        learner = self.make_learner()
        for _ in range(4):
            for region in ("KR", "JP"):
                learner.observe("route_a", responded=True, result_count=4, elapsed_ms=500,
                                region=region, family="event")
                learner.observe("route_b", responded=True, result_count=4, elapsed_ms=500,
                                region=region, family="event")
        learner.observe_selected([
            {"search_method": "route_a", "query_region": "KR", "query_family": "event"}
            for _ in range(8)
        ] + [
            {"search_method": "route_b", "query_region": "JP", "query_family": "event"}
            for _ in range(8)
        ])
        self.assertEqual(
            learner.ordered_routes(["route_a", "route_b"], region="KR", family="event", budget=2)[0],
            "route_a",
        )
        self.assertEqual(
            learner.ordered_routes(["route_a", "route_b"], region="JP", family="event", budget=2)[0],
            "route_b",
        )


if __name__ == "__main__":
    unittest.main()

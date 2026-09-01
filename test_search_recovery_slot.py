import tempfile
import unittest
from pathlib import Path

from search_method_learning import SearchMethodLearner


class RecoverySlotTests(unittest.TestCase):
    def test_transient_cooling_route_gets_periodic_recovery_slot(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            learner = SearchMethodLearner(root / "m.json", root / "b.json")
            learner.start_run()
            # Timeout needs a short failure streak before entering cooldown.
            learner.observe("transient", responded=False, result_count=0, error="TimeoutError timed out", elapsed_ms=10)
            learner.observe("transient", responded=False, result_count=0, error="TimeoutError timed out", elapsed_ms=10)
            for name in ("a", "b", "c", "d", "e"):
                learner.observe(name, responded=True, result_count=2, elapsed_ms=10)
            learner.data["rotation"] = 4
            ordered = learner.ordered_routes(["transient", "a", "b", "c", "d", "e"], budget=5)
            self.assertEqual(len(ordered), 5)
            self.assertIn("transient", ordered)
            self.assertEqual(ordered[-1], "transient")

    def test_http_403_route_is_not_reprobed_during_cooldown(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            learner = SearchMethodLearner(root / "m.json", root / "b.json")
            learner.start_run()
            learner.observe("blocked", responded=False, result_count=0, error="HTTP Error 403 Forbidden", elapsed_ms=10)
            for name in ("a", "b", "c", "d", "e"):
                learner.observe(name, responded=True, result_count=2, elapsed_ms=10)
            learner.data["rotation"] = 4
            ordered = learner.ordered_routes(["blocked", "a", "b", "c", "d", "e"], budget=5)
            self.assertEqual(len(ordered), 5)
            self.assertNotIn("blocked", ordered)


if __name__ == "__main__":
    unittest.main()

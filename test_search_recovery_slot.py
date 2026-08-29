import tempfile
import unittest
from pathlib import Path

from search_method_learning import SearchMethodLearner


class RecoverySlotTests(unittest.TestCase):
    def test_cooling_route_gets_periodic_recovery_slot(self):
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
            self.assertIn("blocked", ordered)
            self.assertEqual(ordered[-1], "blocked")


if __name__ == "__main__":
    unittest.main()

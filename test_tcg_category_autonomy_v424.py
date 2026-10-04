import unittest
from pathlib import Path

import tcg_category_autonomy as controller
import tcg_game_registry as registry


ROOT = Path(__file__).resolve().parent


class TabletCategoryAutonomyV424Tests(unittest.TestCase):
    def test_report_is_ready_and_evidence_bounded(self):
        report = controller.build_report(ROOT)
        self.assertEqual("ready", report["status"])
        self.assertGreaterEqual(report["active_count"], 3)
        self.assertFalse(report["neural_controller"]["active"])
        self.assertFalse(report["neural_controller"]["promotion_allowed"])
        self.assertTrue(report["safety_gates"]["registry_valid"])
        self.assertTrue(report["safety_gates"]["registry_only_mutation"])
        self.assertFalse(report["safety_gates"]["profit_guarantee_disabled"] is False)

    def test_non_core_games_never_enable_grading(self):
        data = registry.load_registry(ROOT)
        for row in data["games"]:
            if row["state"] != "core":
                self.assertIs(False, row["capabilities"]["grading"])

    def test_watch_rows_are_observation_only(self):
        report = controller.build_report(ROOT)
        for item in report["action_plan"]["watch"]:
            self.assertEqual("observe", item["action"])
            self.assertIn(item["state"], {"watch"})
        self.assertFalse(report["action_plan"]["self_extension"]["source_code_generation"])

    def test_invalid_policy_is_not_accepted(self):
        data = registry.load_registry(ROOT)
        invalid = dict(data)
        invalid["policy"] = dict(data["policy"])
        invalid["policy"]["profit_guarantee"] = True
        self.assertFalse(registry.validate_registry(invalid))


if __name__ == "__main__":
    unittest.main(verbosity=2)

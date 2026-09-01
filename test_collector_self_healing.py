import tempfile
import unittest
from pathlib import Path

import collector_self_healing as healing


class CollectorSelfHealingTests(unittest.TestCase):
    def test_server_error_prepares_allowlisted_policy_and_rewards_recovery(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "memory.json"
            first = {
                "results": [{
                    "file": "market_prices.json", "ok": True,
                    "collection_errors": ["KREAM: HTTPError: status 500"],
                    "remaining_collection_errors": ["KREAM: HTTPError: status 500"],
                }]
            }
            summary = healing.observe(first, path)
            self.assertEqual(summary["next_policy_prepared"], 1)
            plan = healing.plan_for("market_prices.json", path)
            self.assertIn(plan["policy_id"], healing.POLICIES)
            self.assertLessEqual(plan["max_attempts"], 3)

            second = {
                "results": [{
                    "file": "market_prices.json", "ok": True,
                    "collection_errors": ["KREAM: HTTPError: status 500"],
                    "remaining_collection_errors": [],
                    "recovered_after_retry": True,
                    "self_heal_policy": plan["policy_id"],
                }]
            }
            rewarded = healing.observe(second, path)
            self.assertEqual(rewarded["policy_recovered"], 1)
            self.assertIsNone(healing.plan_for("market_prices.json", path)["policy_id"])

    def test_structure_change_is_quarantined_without_runtime_policy(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "memory.json"
            report = {
                "results": [{
                    "file": "releases.json", "ok": True,
                    "collection_errors": ["ValueError: 공식 페이지에서 검증 가능한 상품을 1건도 읽지 못함"],
                    "remaining_collection_errors": ["ValueError: 공식 페이지에서 검증 가능한 상품을 1건도 읽지 못함"],
                }]
            }
            summary = healing.observe(report, path)
            self.assertEqual(summary["quarantined_for_code_repair"], 1)
            self.assertIsNone(healing.plan_for("releases.json", path)["policy_id"])
            self.assertFalse(healing.public_status(path)["safety"]["source_rewrite"])

    def test_unknown_policy_from_disk_cannot_execute(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "memory.json"
            path.write_text('{"files":{"releases.json":{"pending_policy":"shell"}}}', encoding="utf-8")
            plan = healing.plan_for("releases.json", path)
            self.assertIsNone(plan["policy_id"])
            self.assertEqual(plan["env"], {})


if __name__ == "__main__":
    unittest.main()

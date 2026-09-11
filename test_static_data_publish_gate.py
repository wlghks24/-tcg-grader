from __future__ import annotations

import datetime as dt
import unittest

import static_data_publish_gate as gate


class StaticDataPublishGateTests(unittest.TestCase):
    def test_public_outputs_follow_auto_update_contract(self):
        expected = tuple(output_name for _, _, output_name in gate.auto_update_all.JOBS)
        self.assertEqual(expected, gate.PUBLIC_OUTPUTS)
        self.assertEqual(8, len(gate.PUBLIC_OUTPUTS))
        self.assertIn("grading_company_updates.json", gate.PUBLIC_OUTPUTS)

    def test_expected_topic_matrix_matches_shared_collector_contract(self):
        self.assertGreaterEqual(gate.EXPECTED_TOPIC_CELLS, 207)
        self.assertEqual(
            gate.EXPECTED_TOPIC_CELLS,
            len(__import__("update_promo_events").social_topic_expected_keys()),
        )

    def test_zero_discovered_leads_do_not_equal_unattempted_collection(self):
        promo = {
            "social_topic_expected_cells": gate.EXPECTED_TOPIC_CELLS,
            "social_topic_attempted_cells": gate.EXPECTED_TOPIC_CELLS,
            "social_topic_failed_cells": [],
            "social_topic_undiscovered_cells": [f"cell-{i}" for i in range(gate.EXPECTED_TOPIC_CELLS)],
        }
        social = {
            "topic_query_expected_cells": gate.EXPECTED_TOPIC_CELLS,
            "topic_query_attempted_cells": gate.EXPECTED_TOPIC_CELLS,
        }
        findings = gate.audit_topic_contract(promo, social)
        self.assertFalse(any(x["severity"] == "critical" for x in findings))
        self.assertTrue(any(x["code"] == "TOPIC_NO_LEAD_FOUND" for x in findings))

    def test_unattempted_topic_cell_fails_closed(self):
        promo = {
            "social_topic_expected_cells": gate.EXPECTED_TOPIC_CELLS,
            "social_topic_attempted_cells": gate.EXPECTED_TOPIC_CELLS - 1,
        }
        social = {
            "topic_query_expected_cells": gate.EXPECTED_TOPIC_CELLS,
            "topic_query_attempted_cells": gate.EXPECTED_TOPIC_CELLS - 1,
        }
        findings = gate.audit_topic_contract(promo, social)
        codes = {x["code"] for x in findings if x["severity"] == "critical"}
        self.assertIn("TOPIC_COLLECTION_NOT_FULLY_ATTEMPTED", codes)
        self.assertIn("SOCIAL_TOPIC_ATTEMPT_CONTRACT_MISMATCH", codes)

    def test_provider_failure_is_reported_without_relabeling_zero_result_as_gap(self):
        promo = {
            "social_topic_expected_cells": gate.EXPECTED_TOPIC_CELLS,
            "social_topic_attempted_cells": gate.EXPECTED_TOPIC_CELLS,
            "social_topic_failed_cells": ["나루토 카드/US/movie"],
        }
        social = {
            "topic_query_expected_cells": gate.EXPECTED_TOPIC_CELLS,
            "topic_query_attempted_cells": gate.EXPECTED_TOPIC_CELLS,
        }
        findings = gate.audit_topic_contract(promo, social)
        warning = next(x for x in findings if x["code"] == "TOPIC_PROVIDER_FAILURES_PRESERVED")
        self.assertEqual("warning", warning["severity"])
        self.assertEqual(1, warning["count"])


if __name__ == "__main__":
    unittest.main()

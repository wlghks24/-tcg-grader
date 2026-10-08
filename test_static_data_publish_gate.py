from __future__ import annotations

import datetime as dt
import unittest

import static_data_publish_gate as gate


class StaticDataPublishGateTests(unittest.TestCase):
    def test_invalid_movie_and_purchase_rows_are_identified_without_leaking_urls(self):
        invalid_movie = {
            "game": "포켓몬 카드", "region": "KR", "name_ko": "잘못된" + chr(10) + "행사",
            "start_date": "2026-10-09", "end_date": "2026-10-08",
            "reward": "확인 중", "condition": "공식 확인 중",
            "source": "http://unverified.example",
        }
        found = gate.first_invalid_public_row(
            "promo_events.json", {"items": [invalid_movie], "archive_items": []})
        self.assertEqual(1, found["invalid_record_index"])
        self.assertNotIn(chr(10), found["invalid_record_name"])
        self.assertNotIn("unverified.example", str(found))
        self.assertEqual({}, gate.first_invalid_public_row(
            "promo_events.json", {"items": [], "archive_items": []}))

        invalid_shop = {
            "name": "CU 공개 매장 안내", "region": "KR", "games": ["Pokemon"],
            "type": "official", "channel": "offline", "chain": "CU",
            "retailer_category": "convenience",
            "official_reference_url": "https://example.org/unverified",
            "url": "https://cu.bgfretail.com/",
        }
        found = gate.first_invalid_public_row(
            "purchase_sources.json", {"sources": [invalid_shop]})
        self.assertEqual(1, found["invalid_record_index"])
        self.assertEqual("CU 공개 매장 안내", found["invalid_record_name"])
        self.assertEqual("ValueError", found["invalid_record_error"])
        self.assertNotIn("example.org", str(found))
        self.assertEqual({}, gate.first_invalid_public_row(
            "purchase_sources.json", {"sources": []}))

    def test_invalid_purchase_snapshot_stays_blocked_with_row_diagnostics(self):
        import tempfile
        import json
        from pathlib import Path
        from unittest import mock
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "purchase_sources.json").write_text(json.dumps({
                "sources": [{
                    "name": "CU official", "region": "KR", "games": ["Pokemon"],
                    "type": "official", "channel": "offline", "chain": "CU",
                    "retailer_category": "convenience",
                    "official_reference_url": "https://example.org/store",
                    "url": "https://cu.bgfretail.com/",
                }]
            }), encoding="utf-8")
            with mock.patch.object(gate, "PUBLIC_OUTPUTS", ("purchase_sources.json",)):
                result = gate.verify(root)
        rows = [row for row in result["findings"]
                if row.get("code") == "INVALID_PUBLIC_OUTPUT"]
        self.assertEqual(1, len(rows))
        self.assertEqual("critical", rows[0]["severity"])
        self.assertEqual(1, rows[0]["invalid_record_index"])
        self.assertFalse(result["publish_allowed"])

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

    def test_expanded_official_games_do_not_become_unattempted_social_cells(self):
        import update_promo_events as promo

        collector = promo.multi_route_event_discovery
        expected_keys = {
            f"{game}/{region}/{topic}"
            for game in collector.GAMES
            for region in collector.REGIONS
            for topic in collector.COVERAGE_TOPICS
        }
        self.assertEqual(set(promo.social_topic_expected_keys()), expected_keys)
        self.assertEqual(gate.EXPECTED_TOPIC_CELLS, len(expected_keys))
        # Promoted titles remain covered by separate official discovery,
        # not imaginary extra jobs in the core social discovery matrix.
        self.assertTrue(set(collector.GAMES).issubset(set(promo.GAMES)))
        for game in set(promo.GAMES) - set(collector.GAMES):
            self.assertFalse(any(key.startswith(f"{game}/") for key in expected_keys))

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

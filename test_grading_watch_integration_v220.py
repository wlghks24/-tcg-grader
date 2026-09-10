from __future__ import annotations

import copy
from pathlib import Path
import unittest

import auto_repair_engine
import auto_update_all
import grading_company_watch
import tcg_updater
import verified_collection_job_neural


class GradingWatchIntegrationV220Tests(unittest.TestCase):
    def _snapshot(self):
        sources = {}
        for company, specs in grading_company_watch.WATCH_SOURCES.items():
            for spec in specs:
                sources[spec["id"]] = {
                    "company": company,
                    "source_id": spec["id"],
                    "kind": spec["kind"],
                    "market": spec["market"],
                    "currency": spec["currency"],
                    "url": spec["url"],
                    "status": "ok",
                    "verified_official_source": True,
                    "services": [],
                    "announcements": [],
                }
        return {
            "schema_version": 1,
            "checked_at": "2026-09-11T00:00:00+00:00",
            "policy": {
                "official_sources_only": True,
                "community_posts_are_leads_only": True,
                "last_good_retained_on_failure": True,
                "automatic_source_code_mutation": False,
            },
            "summary": {
                "companies": 5,
                "sources": len(sources),
                "healthy_sources": len(sources),
                "degraded_sources": 0,
                "new_changes": 0,
            },
            "companies": {
                name: {"markets": {}, "source_health": []}
                for name in ("PSA", "BGS", "CGC", "TAG", "BRG")
            },
            "sources": sources,
            "announcements": [],
            "recent_changes": [],
            "history": [],
        }

    def test_mandatory_local_collection_contains_grading_watch_exactly_once(self):
        rows = [row for row in auto_update_all.JOBS if row[2] == "grading_company_updates.json"]
        self.assertEqual(1, len(rows))
        self.assertEqual("grading_company_watch", rows[0][1])
        self.assertEqual(8, len(auto_update_all.JOBS))
        self.assertEqual(len(auto_update_all.JOBS), tcg_updater._full_update_job_count())

    def test_job_neural_cannot_omit_mandatory_grading_collection(self):
        self.assertIn("grading_company_updates.json", verified_collection_job_neural.JOB_KEYS)
        self.assertTrue(verified_collection_job_neural.SAFETY["all_mandatory_collectors_preserved"])
        self.assertFalse(verified_collection_job_neural.SAFETY["collector_skip_allowed"])

    def test_grading_snapshot_requires_official_policy_and_hosts(self):
        good = self._snapshot()
        auto_update_all.validate_json("grading_company_updates.json", good)
        self.assertTrue(auto_repair_engine._valid_project_payload("grading_company_updates.json", good))

        external = copy.deepcopy(good)
        next(iter(external["sources"].values()))["url"] = "https://example.invalid/fake-grading-price"
        with self.assertRaises(ValueError):
            auto_update_all.validate_json("grading_company_updates.json", external)
        self.assertFalse(auto_repair_engine._valid_project_payload("grading_company_updates.json", external))

        unverified = copy.deepcopy(good)
        unverified["recent_changes"] = [{"verified_official_source": False}]
        with self.assertRaises(ValueError):
            auto_update_all.validate_json("grading_company_updates.json", unverified)
        self.assertFalse(auto_repair_engine._valid_project_payload("grading_company_updates.json", unverified))

    def test_static_refresh_is_independent_recovery_lane(self):
        static = Path(".github/workflows/tcg-static-data-refresh.yml").read_text(encoding="utf-8")
        dedicated = Path(".github/workflows/grading-company-watch.yml").read_text(encoding="utf-8")
        self.assertIn("grading_company_watch.py", static)
        self.assertIn("test_grading_company_watch_v215.py", static)
        self.assertIn("grading_company_updates.json graded_photo_candidates.json", static)
        self.assertIn("cron: '47 */6 * * *'", static)
        self.assertIn("cron: '23 */3 * * *'", dedicated)

    def test_feature_contract_and_code_map_use_expanded_collection_contract(self):
        contract = Path("feature_contract.py").read_text(encoding="utf-8")
        self.assertIn("8단계 자동수집", contract)
        self.assertNotIn("\"'total':7\" in server", contract)
        code_map = Path("code_map_intelligence.py").read_text(encoding="utf-8")
        self.assertIn("auto_update_all.py", code_map)
        self.assertIn("verified_collection_job_neural.py", code_map)
        self.assertIn("월요일 19:00 제작", code_map)
        self.assertIn("매시간 수집", code_map)


if __name__ == "__main__":
    unittest.main()

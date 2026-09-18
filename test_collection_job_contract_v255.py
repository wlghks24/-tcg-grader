import unittest
from pathlib import Path

import auto_update_all
import collection_job_contract as contract
import tcg_updater
import runtime_bundle_guard_v143 as bundle_guard
import tablet_runtime_manifest as tablet_manifest


ROOT = Path(__file__).resolve().parent


class CollectionJobContractV255Tests(unittest.TestCase):
    def test_one_ssot_defines_exact_eight_mandatory_jobs(self):
        expected_outputs = (
            "releases.json",
            "market_watch.json",
            "market_prices.json",
            "promo_events.json",
            "purchase_sources.json",
            "exchange_rates.json",
            "grading_company_updates.json",
            "graded_photo_candidates.json",
        )
        self.assertEqual(contract.JOB_COUNT, 8)
        self.assertEqual(contract.MANDATORY_OUTPUTS, expected_outputs)
        self.assertEqual(tuple(auto_update_all.JOBS), contract.COLLECTION_JOBS)

    def test_server_idle_and_running_totals_use_same_contract(self):
        self.assertEqual(tcg_updater.UPDATE_JOB["total"], contract.JOB_COUNT)
        self.assertEqual(tcg_updater._full_update_job_count(), contract.JOB_COUNT)
        source = (ROOT / "tcg_updater.py").read_text(encoding="utf-8")
        self.assertNotIn("'current':0,'total':7", source)
        self.assertIn("COLLECTION_JOB_COUNT", source)

    def test_runtime_and_tablet_bundles_require_contract(self):
        self.assertIn("collection_job_contract.py", bundle_guard.REQUIRED_FILES)
        self.assertIn("collection_job_contract.py", tablet_manifest.ACTIVE_RUNTIME_FILES)
        self.assertEqual(bundle_guard.EXPECTED_JOB_FILES, set(contract.MANDATORY_OUTPUTS))

    def test_feature_contract_uses_current_eight_stage_name(self):
        source = (ROOT / "feature_contract.py").read_text(encoding="utf-8")
        self.assertIn('add("eight_collection_jobs"', source)
        self.assertNotIn('add("six_collection_jobs"', source)
        self.assertIn("collection_job_contract.py", source)

    def test_legacy_seven_stage_mutation_path_is_removed(self):
        self.assertFalse((ROOT / "apply_graded_photo_collection_patch.py").exists())
        self.assertFalse((ROOT / ".github/workflows/apply-graded-photo-collection.yml").exists())


if __name__ == "__main__":
    unittest.main()

"""V660 synthetic-only V376 journal triple-correlation safety tests."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from execution.tablet_autonomy_execution_correlation_v660 import inspect, JOURNAL_NAME
from execution import tablet_autonomy_collection_receipts_v653 as v653

class CorrelationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = datetime.now(timezone.utc)
        self.started = self.now - timedelta(minutes=5)
        self.finished = self.now - timedelta(minutes=3)
        self.journal = {
            "schema_version": 6, "controller_version": "v376",
            "status": "COMMITTED", "cycle_id": "a"*64,
            "plan_sha256": "b"*64,
            "selected_recipe": "RECOVER_SOURCE_HEALTH",
            "selected_skill_id": "skill-1",
            "prepared_at": self.started.isoformat(),
            "executed_at": (self.started + timedelta(minutes=1)).isoformat(),
            "committed_at": self.finished.isoformat(),
            "operational_status": "OPERATIONAL_REFRESH_EXECUTED",
            "skill_state_status": "SKILL_STATE_SAVED",
            "git_write": False, "source_code_modified": False,
        }
        self.write(self.root / JOURNAL_NAME, self.journal)
        self.write(self.root / "auto_update_report.json", {
            "trigger": "tablet-v374-autonomous-refresh",
            "started_at": self.started.isoformat(),
            "finished_at": self.finished.isoformat(),
        })

    def write(self, path, value):
        path.write_text(json.dumps(value, ensure_ascii=False))

    def correlated(self):
        _, digest = v653._load(self.root / "auto_update_report.json")
        return {
            "status": "LOCAL_EXECUTION_CORRELATED_UNVERIFIED",
            "collector_report_sha256": digest,
            "trial": {"trial_id": "skill-1",
                      "action_id": "RECHECK_DEGRADED_SOURCES"},
        }

    def inspect_with(self, prior=None):
        with mock.patch(
            "execution.tablet_autonomy_execution_correlation_v660.v656.inspect",
            return_value=self.correlated() if prior is None else prior
        ):
            return inspect(self.root, now=self.now)

    def test_three_way_match_only_unverified(self):
        old = {p.name: p.read_bytes() for p in self.root.iterdir()}
        result = self.inspect_with()
        self.assertEqual("LOCAL_THREE_WAY_CORRELATED_UNVERIFIED", result["status"])
        self.assertEqual(0, result["verified_outcomes_created"])
        self.assertFalse(result["independent_external_attestation"])
        self.assertFalse(result["eligible_for_v373_training"])
        self.assertEqual(old, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_missing_journal_blocks(self):
        (self.root / JOURNAL_NAME).unlink()
        self.assertEqual("MISSING_OR_UNSAFE_JOURNAL", self.inspect_with()["reason"])

    def test_symlink_journal_blocks(self):
        p = self.root / JOURNAL_NAME
        real = self.root / "real"
        p.rename(real)
        p.symlink_to(real)
        self.assertEqual("MISSING_OR_UNSAFE_JOURNAL", self.inspect_with()["reason"])

    def test_prepared_not_success(self):
        self.journal["status"] = "PREPARED"
        self.write(self.root / JOURNAL_NAME, self.journal)
        self.assertEqual("JOURNAL_NOT_COMMITTED", self.inspect_with()["reason"])

    def test_uncommitted_not_success(self):
        self.journal["status"] = "EXECUTED_UNCOMMITTED"
        self.write(self.root / JOURNAL_NAME, self.journal)
        self.assertEqual("JOURNAL_NOT_COMMITTED", self.inspect_with()["reason"])

    def test_failed_operation_not_success(self):
        self.journal["operational_status"] = "OPERATIONAL_REFRESH_FAILED"
        self.write(self.root / JOURNAL_NAME, self.journal)
        self.assertEqual("JOURNAL_NOT_PROVEN_SAFE_EXECUTION", self.inspect_with()["reason"])

    def test_git_mutation_disallowed(self):
        self.journal["git_write"] = True
        self.write(self.root / JOURNAL_NAME, self.journal)
        self.assertEqual("JOURNAL_NOT_PROVEN_SAFE_EXECUTION", self.inspect_with()["reason"])

    def test_action_mismatch_blocks(self):
        data = self.correlated()
        data["trial"]["trial_id"] = "unrelated"
        self.assertEqual("JOURNAL_TRIAL_ACTION_MISMATCH", self.inspect_with(data)["reason"])

    def test_recipe_mismatch_blocks(self):
        self.journal["selected_recipe"] = "OBSERVE_ONLY"
        self.write(self.root / JOURNAL_NAME, self.journal)
        self.assertEqual("INVALID_JOURNAL_ACTION", self.inspect_with()["reason"])

    def test_malformed_array_recipe_cannot_crash_audit(self):
        self.journal["selected_recipe"] = ["RECOVER_SOURCE_HEALTH"]
        self.write(self.root / JOURNAL_NAME, self.journal)
        self.assertEqual("INVALID_JOURNAL_ACTION", self.inspect_with()["reason"])

    def test_malformed_object_recipe_cannot_crash_audit(self):
        self.journal["selected_recipe"] = {"recipe": "RECOVER_SOURCE_HEALTH"}
        self.write(self.root / JOURNAL_NAME, self.journal)
        self.assertEqual("INVALID_JOURNAL_ACTION", self.inspect_with()["reason"])

    def test_clock_reversal_blocks(self):
        self.journal["committed_at"] = (self.started - timedelta(minutes=1)).isoformat()
        self.write(self.root / JOURNAL_NAME, self.journal)
        self.assertEqual("INCONSISTENT_JOURNAL_TIMELINE", self.inspect_with()["reason"])

    def test_unrelated_collector_time_blocks(self):
        self.journal["executed_at"] = (self.started - timedelta(hours=1)).isoformat()
        self.journal["prepared_at"] = (self.started - timedelta(hours=2)).isoformat()
        self.write(self.root / JOURNAL_NAME, self.journal)
        self.assertEqual("JOURNAL_COLLECTOR_TIME_MISMATCH", self.inspect_with()["reason"])

    def test_fake_sha_blocks(self):
        self.journal["cycle_id"] = "bogus"
        self.write(self.root / JOURNAL_NAME, self.journal)
        self.assertEqual("INVALID_JOURNAL_DIGEST", self.inspect_with()["reason"])

    def test_duplicate_json_key_blocks(self):
        p = self.root / JOURNAL_NAME
        p.write_text(p.read_text().replace('"status": "COMMITTED",', '"status": "COMMITTED", "status": "COMMITTED",'))
        self.assertEqual("INVALID_JOURNAL", self.inspect_with()["reason"])

    def test_collector_uncorrelated_remains_held(self):
        r = self.inspect_with({"status": "EVIDENCE_HOLD", "reason": "MISSING_PROOF"})
        self.assertEqual("COLLECTOR_TRIAL_MISSING_PROOF", r["reason"])

    def test_ordering_and_23pm_schedule_unchanged(self):
        root = Path(__file__).resolve().parents[1]
        s = (root / "TABLET_SCHEDULED_UPDATE.sh").read_text()
        triple = "python -m execution.tablet_autonomy_execution_correlation_v660 --root"
        pending = "python -m execution.tablet_autonomy_pending_trial_guard_v653 --root"
        execute = "python tablet_autonomous_evolution_v400.py --domain tablet_gpt"
        self.assertLess(s.index(triple), s.index(pending))
        self.assertLess(s.index(pending), s.index(execute))
        self.assertIn('SCHEDULE_HOUR="23"', s)
        self.assertNotIn("reset --hard", s)

if __name__ == "__main__":
    unittest.main()

"""V653 no-op/pending-trial safety tests; never executes or generates learning."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from execution.tablet_autonomy_pending_trial_guard_v653 import inspect


class TrialProvenanceGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / "tablet_autonomy_skills_v374.json"

    def write(self, pending=None, **changes):
        data = {"schema_version": 4, "controller_version": "v374",
                "active_skills": [], "pending_trials": pending or [],
                "suspended_recipes": [], "updated_at": None}
        data.update(changes)
        self.state.write_text(json.dumps(data), encoding="utf-8")

    def test_missing_clean_bootstrap_does_not_create_evidence(self):
        out = inspect(self.root)
        self.assertTrue(out["allow_autonomy"])
        self.assertEqual("NO_PENDING_TRIALS", out["status"])
        self.assertFalse(self.state.exists())

    def test_empty_well_formed_state_is_allowed(self):
        self.write()
        self.assertTrue(inspect(self.root)["allow_autonomy"])

    def test_unattested_action_is_held_regardless_of_elapsed_time(self):
        self.write([{"recipe": "RECOVER_FRESHNESS",
                     "created_at": "2026-10-01T00:00:00+00:00",
                     "expires_at": "2026-10-02T00:00:00+00:00",
                     "before": {"freshness": "stale"},
                     "execution": {"status": "RESOURCE_HOLD", "executed": False}}])
        out = inspect(self.root)
        self.assertFalse(out["allow_autonomy"])
        self.assertEqual("UNATTESTED_PENDING_TRIALS", out["reason"])
        self.assertEqual(0, out["verified_outcomes_created"])

    def test_self_claimed_verified_flag_does_not_bypass(self):
        self.write([{"recipe": "RECOVER_SOURCE_HEALTH", "verified": True,
                     "execution_receipt": {"verified": True, "executed": True}}])
        self.assertFalse(inspect(self.root)["allow_autonomy"])

    def test_corrupt_json_fails_closed(self):
        self.state.write_text("{bad", encoding="utf-8")
        self.assertEqual("INVALID_OR_UNREADABLE", inspect(self.root)["reason"])

    def test_corrupt_schema_fails_closed(self):
        self.write(schema_version=5)
        self.assertEqual("INVALID_V374_SKILL_STATE", inspect(self.root)["reason"])

    def test_symlink_fails_closed(self):
        target = self.root / "untrusted.json"
        target.write_text("{}", encoding="utf-8")
        self.state.symlink_to(target)
        self.assertEqual("UNSAFE_SYMLINK", inspect(self.root)["reason"])

    def test_over_limit_pending_fails_closed(self):
        self.write([{} for _ in range(9)])
        self.assertEqual("INVALID_V374_SKILL_STATE", inspect(self.root)["reason"])

    def test_idempotent_read_only_and_preservation(self):
        self.write([{"recipe": "RECOVER_FRESHNESS", "before": {}}])
        raw = self.state.read_bytes()
        one = inspect(self.root)
        two = inspect(self.root)
        self.assertEqual(one, two)
        self.assertEqual(raw, self.state.read_bytes())

    def test_scheduler_runs_guard_before_mutating_v400(self):
        source = (Path(__file__).resolve().parents[1] / "TABLET_SCHEDULED_UPDATE.sh").read_text(encoding="utf-8")
        guard = 'python -m execution.tablet_autonomy_pending_trial_guard_v653 --root "$ROOT"'
        mutation = 'python tablet_autonomous_evolution_v400.py --domain tablet_gpt --execute-safe-learning'
        self.assertIn(guard, source)
        self.assertIn(mutation, source)
        self.assertLess(source.index(guard), source.index(mutation))
        self.assertIn('write_autonomy_status "TRIAL_PROVENANCE_HOLD"', source)


if __name__ == "__main__":
    unittest.main()

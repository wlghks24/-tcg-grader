"""V654: no synthetic verified sample from merely healthy collector metadata."""
from datetime import datetime, timezone
import json
import tempfile
import unittest
from pathlib import Path
from execution.tablet_autonomy_observation_v654 import inspect, cycle, REQUIRED_RESULTS

NOW = datetime(2026, 10, 19, 11, 0, tzinfo=timezone.utc)


class PassiveEvidenceV654Tests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.state = self.root / "local" / "observations.json"

    def seed(self, *, ok=True, date="2026-10-19T10:30:00+00:00", files=None):
        (self.root / "tcg_live_data.json").write_text(json.dumps({
            "auto_update": {"report_ok": ok, "full_update": True,
                            "last_run": date, "trigger": "automatic",
                            "source_error_count": 0}
        }))
        (self.root / "auto_update_report.json").write_text(json.dumps({
            "ok": ok, "results": [{"file": p, "status": "ok"}
                                   for p in (files if files is not None else REQUIRED_RESULTS)]
        }))

    def test_observation_from_real_output_claims_is_not_verified_learning(self):
        self.seed()
        v = cycle(self.root, self.state, capture=True, now=NOW)
        self.assertEqual("OBSERVATION_SAVED_NOT_VERIFIED", v["status"])
        r = json.loads(self.state.read_text())["observations"][0]
        self.assertIs(False, r["verified"])
        self.assertIs(False, r["causal_proof"])
        self.assertIs(False, r["confidence_eligible"])
        self.assertIsNone(r["training_reward"])
        self.assertEqual(0, v["verified_training_samples_added"])
        self.assertFalse((self.root / "tablet_autonomy_verified_outcomes.jsonl").exists())
        self.assertFalse((self.root / "tablet_autonomy_skills_v374.json").exists())

    def test_repeated_run_id_and_hash_does_not_create_duplicate(self):
        self.seed()
        cycle(self.root, self.state, capture=True, now=NOW)
        second = cycle(self.root, self.state, capture=True, now=NOW)
        self.assertEqual("ALREADY_OBSERVED", second["status"])
        self.assertEqual(1, len(json.loads(self.state.read_text())["observations"]))

    def test_new_completed_run_creates_second_observation_not_a_reward(self):
        self.seed()
        cycle(self.root, self.state, capture=True, now=NOW)
        self.seed(date="2026-10-19T10:50:00+00:00")
        result = cycle(self.root, self.state, capture=True, now=NOW)
        self.assertEqual(2, result["storage"]["count"])
        self.assertEqual(0, result["verified_training_samples_added"])

    def test_report_failure_never_creates_evidence(self):
        self.seed(ok=False)
        self.assertEqual("SOURCE_EVIDENCE_HOLD", cycle(self.root, self.state, capture=True, now=NOW)["status"])
        self.assertFalse(self.state.exists())

    def test_missing_source_data_remains_hold(self):
        self.assertEqual("SOURCE_EVIDENCE_HOLD", inspect(self.root, now=NOW)["status"])

    def test_stale_and_future_runs_are_held(self):
        for date in ["2026-10-11T10:00:00+00:00", "2026-10-19T16:00:00+00:00", "yesterday"]:
            self.seed(date=date)
            self.assertEqual("SOURCE_EVIDENCE_HOLD", inspect(self.root, now=NOW)["status"])

    def test_missing_and_duplicate_expected_file_are_held(self):
        self.seed(files=["releases.json"])
        self.assertEqual("SOURCE_EVIDENCE_HOLD", inspect(self.root, now=NOW)["status"])
        self.seed(files=list(REQUIRED_RESULTS) + ["releases.json"])
        self.assertEqual("SOURCE_EVIDENCE_HOLD", inspect(self.root, now=NOW)["status"])

    def test_symlink_and_corruption_do_not_overwrite_previous_state(self):
        self.seed()
        self.state.parent.mkdir()
        self.state.write_text('{"bad":true}')
        before = self.state.read_bytes()
        self.assertEqual("CORRUPT_STATE_HOLD", cycle(self.root, self.state, capture=True, now=NOW)["status"])
        self.assertEqual(before, self.state.read_bytes())
        self.state.unlink()
        self.state.symlink_to(self.root / "absent")
        self.assertEqual("UNSAFE_STATE_PATH_HOLD", cycle(self.root, self.state, capture=True, now=NOW)["status"])

    def test_source_symlinks_fail_closed(self):
        self.seed()
        p = self.root / "tcg_live_data.json"
        p.unlink()
        p.symlink_to(self.root / "auto_update_report.json")
        self.assertEqual("SOURCE_EVIDENCE_HOLD", inspect(self.root, now=NOW)["status"])

    def test_inspection_mode_does_not_write_even_with_valid_run(self):
        self.seed()
        self.assertEqual("PASSIVE_OBSERVATION_READY", cycle(self.root, self.state, now=NOW)["status"])
        self.assertFalse(self.state.exists())

    def test_scheduler_invokes_passive_stage_after_v400_without_new_schedule(self):
        s = (Path(__file__).resolve().parents[1] / "TABLET_SCHEDULED_UPDATE.sh").read_text()
        self.assertIn("execution.tablet_autonomy_observation_v654", s)
        self.assertIn("--capture", s)
        self.assertIn('SCHEDULE_HOUR="23"', s)
        self.assertIn('return "$rc"', s)
        self.assertNotIn("reset --hard", s)


if __name__ == "__main__":
    unittest.main()

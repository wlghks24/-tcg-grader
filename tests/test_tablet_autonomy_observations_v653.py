"""V653: unverified real evidence capture is never promoted into learning."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import execution.tablet_autonomy_observations_v653 as tool

NOW = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)
HEAD = "a" * 40


class TabletObservationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.log = self.root / "autonomy-20261019-230000.log"
        self.journal = self.root / "journal.json"
        self.valid = {
            "v400_status": "V400_UPSTREAM_HOLD",
            "v387_uncertainty_policy": {
                "selected_action": "TRAIN_QUERY_STRATEGY",
                "selected_confidence": 0.3852,
                "confidence_threshold": 0.55,
            },
            "v387_autonomous_gate": {"status": "V387_UNCERTAINTY_HOLD", "allow_execution": False},
            "execution": {"executed": False, "git_write": False, "source_code_modified": False},
        }
        self.log.write_text("preflight okay\n" + json.dumps(self.valid) + "\n", encoding="utf-8")
        self.head_patch = mock.patch.object(tool, "_head_sha", return_value=HEAD)
        self.head_patch.start()
        self.addCleanup(self.head_patch.stop)

    def record(self):
        return tool.observe(self.root, self.log, NOW)

    def test_records_real_log_hash_not_verified_outcome(self):
        row = self.record()
        self.assertEqual("UNVERIFIED_RUNTIME_OBSERVATION_ONLY", row["classification"])
        self.assertEqual(HEAD, row["git_head_sha"])
        self.assertEqual(0.3852, row["reported_confidence"])
        self.assertFalse(row["verified_training_outcome"])
        self.assertFalse(row["trust_increase_authorized"])
        self.assertFalse(row["may_promote_to_v373_outcome"])

    def test_missing_and_corrupt_log_refused(self):
        self.log.unlink()
        self.assertEqual("EVIDENCE_CAPTURE_HOLD", self.record()["status"])
        self.log.write_text("not json\n", encoding="utf-8")
        self.assertEqual("V400_LOG_JSON_MISSING", self.record()["reason"])

    def test_no_report_digest_claims_success(self):
        self.assertEqual("MISSING_OR_UNSAFE", self.record()["source_reports"]["COLLECTION_VERIFICATION_REPORT.json"]["status"])
        (self.root / "COLLECTION_VERIFICATION_REPORT.json").write_text('{"status":"pass"}')
        info = self.record()["source_reports"]["COLLECTION_VERIFICATION_REPORT.json"]
        self.assertEqual("PARSEABLE_UNVERIFIED", info["status"])
        self.assertEqual(64, len(info["sha256"]))

    def test_symlinked_source_is_unusable(self):
        (self.root / "COLLECTION_VERIFICATION_REPORT.json").symlink_to(self.log)
        self.assertEqual("MISSING_OR_UNSAFE", self.record()["source_reports"]["COLLECTION_VERIFICATION_REPORT.json"]["status"])

    def test_saves_only_local_unverified_journal_then_dedupes(self):
        row = self.record()
        a = tool.persist_observation(self.journal, row)
        b = tool.persist_observation(self.journal, row)
        self.assertEqual("OBSERVATION_SAVED_UNVERIFIED", a["status"])
        self.assertEqual("ALREADY_OBSERVED", b["status"])
        stored = json.loads(self.journal.read_text())
        self.assertEqual(1, len(stored["observations"]))
        self.assertFalse(stored["training_promotion_authorized"])

    def test_corrupt_journal_is_never_overwritten(self):
        self.journal.write_text("{corrupt\n")
        old = self.journal.read_bytes()
        outcome = tool.persist_observation(self.journal, self.record())
        self.assertEqual("CORRUPT_OR_SYMLINK_HOLD", outcome["status"])
        self.assertEqual(old, self.journal.read_bytes())

    def test_symlinked_journal_is_not_followed(self):
        destination = self.root / "target"
        destination.write_text("sensitive")
        self.journal.symlink_to(destination)
        result = tool.persist_observation(self.journal, self.record())
        self.assertEqual("UNSAFE_JOURNAL_PATH_HOLD", result["status"])
        self.assertEqual("sensitive", destination.read_text())

    def test_never_accepts_verified_training_promotion(self):
        forged = dict(self.record(), verified_training_outcome=True)
        self.assertEqual("UNSAFE_PROMOTION_HOLD", tool.persist_observation(self.journal, forged)["status"])
        self.assertFalse(self.journal.exists())

    def test_capture_does_not_write_without_persist(self):
        before = set(self.root.iterdir())
        self.record()
        self.assertEqual(before, set(self.root.iterdir()))

    def test_finite_capacity_holds_without_deleting_history(self):
        row = self.record()
        payload = {"schema_version": 1, "training_promotion_authorized": False,
                   "observations": [dict(row, log_sha256=str(i).zfill(64)) for i in range(tool.MAX_OBSERVATIONS)]}
        self.journal.write_text(json.dumps(payload), encoding="utf-8")
        before = self.journal.read_bytes()
        result = tool.persist_observation(self.journal, row)
        self.assertEqual("JOURNAL_CAPACITY_HOLD", result["status"])
        self.assertEqual(before, self.journal.read_bytes())

    def test_scheduler_keeps_2300_and_original_v400_status(self):
        scheduler = (Path(__file__).resolve().parents[1] / "TABLET_SCHEDULED_UPDATE.sh").read_text(encoding="utf-8")
        self.assertIn('SCHEDULE_HOUR="23"', scheduler)
        self.assertIn('SCHEDULE_MINUTE="00"', scheduler)
        self.assertIn("execution.tablet_autonomy_observations_v653", scheduler)
        self.assertIn('return "$rc"', scheduler)
        self.assertNotIn("reset --hard", scheduler)


if __name__ == "__main__":
    unittest.main()

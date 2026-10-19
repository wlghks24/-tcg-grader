"""V654 regression: actual scheduled logs are observations, never training rows."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from execution.tablet_autonomy_evidence_journal_v654 import EvidenceHold, OUTPUT_NAME, record, status


class RealLogObservationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "logs").mkdir()
        self.log = self.root / "logs" / "autonomy-20261019-230000.log"
        self.sha = "a" * 40
        self.write_log()

    def write_log(self, value=None):
        if value is None:
            value = {"v400_status": "V400_UPSTREAM_HOLD", "execution": {"executed": False},
                     "v387_uncertainty_policy": {"selected_action": "TRAIN_QUERY_STRATEGY",
                                                "selected_confidence": 0.3852},
                     "v387_autonomous_gate": {"status": "V387_UNCERTAINTY_HOLD"}}
        self.log.write_text("preflight PASS\n" + json.dumps(value) + "\n", encoding="utf-8")

    def invoke(self):
        return record(self.root, self.log, self.sha, "EVIDENCE_BOOTSTRAP_HOLD")

    def read(self):
        return json.loads((self.root / OUTPUT_NAME).read_text(encoding="utf-8"))

    def test_actual_log_hash_is_persisted_but_never_training(self):
        result = self.invoke()
        self.assertEqual("OBSERVATION_RECORDED_UNVERIFIED", result["status"])
        data = self.read()
        row = data["observations"][0]
        self.assertEqual("UNVERIFIED_RUNTIME_OBSERVATION", row["kind"])
        self.assertIs(row["verified"], False)
        self.assertIs(row["eligible_for_training"], False)
        self.assertIs(row["causal_improvement_proven"], False)
        self.assertEqual(self.sha, row["local_main_sha"])
        self.assertEqual(0.3852, row["reported_confidence"])
        self.assertFalse((self.root / "tablet_autonomy_verified_outcomes.jsonl").exists())

    def test_exact_replay_is_idempotent(self):
        self.invoke()
        self.assertEqual("ALREADY_RECORDED", self.invoke()["status"])
        self.assertEqual(1, self.read()["total_observations"])

    def test_mutated_log_replay_is_held(self):
        self.invoke()
        self.write_log({"v400_status": "V400_VERIFIED_ALLOW"})
        with self.assertRaisesRegex(EvidenceHold, "SOURCE_LOG_CHANGED"):
            self.invoke()

    def test_tampered_journal_refuses_overwrite(self):
        self.invoke()
        path = self.root / OUTPUT_NAME
        data = self.read()
        data["observations"][0]["reported_confidence"] = 0.9
        path.write_text(json.dumps(data), encoding="utf-8")
        before = path.read_bytes()
        with self.assertRaisesRegex(EvidenceHold, "JOURNAL_CHAIN"):
            self.invoke()
        self.assertEqual(before, path.read_bytes())

    def test_untrusted_trust_upgrade_is_held(self):
        self.invoke()
        path = self.root / OUTPUT_NAME
        data = self.read()
        data["observations"][0]["verified"] = True
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(EvidenceHold):
            status(self.root)

    def test_symlinked_log_is_held(self):
        target = self.root / "target"
        target.write_text("junk", encoding="utf-8")
        self.log.unlink()
        self.log.symlink_to(target)
        with self.assertRaisesRegex(EvidenceHold, "UNSAFE_LOG"):
            self.invoke()

    def test_symlinked_output_is_held(self):
        dest = self.root / "external"
        dest.write_text("private", encoding="utf-8")
        (self.root / OUTPUT_NAME).symlink_to(dest)
        with self.assertRaisesRegex(EvidenceHold, "JOURNAL_SYMLINK"):
            self.invoke()
        self.assertEqual("private", dest.read_text())

    def test_log_path_outside_state_is_held(self):
        path = self.root / "autonomy-20261019-230000.log"
        path.write_text("test", encoding="utf-8")
        with self.assertRaisesRegex(EvidenceHold, "UNSAFE_LOG"):
            record(self.root, path, self.sha, "FAILED")

    def test_invalid_main_sha_is_held(self):
        with self.assertRaisesRegex(EvidenceHold, "INVALID_MAIN_SHA"):
            record(self.root, self.log, "ff47c9", "FAILED")

    def test_precheck_failure_is_observed_not_verified(self):
        self.write_log({"unrelated": "precheck"})
        self.invoke()
        row = self.read()["observations"][0]
        self.assertEqual("NO_STRUCTURED_V400", row["v400_status"])
        self.assertFalse(row["eligible_for_training"])

    def test_status_is_read_only(self):
        self.invoke()
        before = (self.root / OUTPUT_NAME).read_bytes()
        self.assertEqual("OBSERVATION_ONLY_NOT_TRAINING", status(self.root)["status"])
        self.assertEqual(before, (self.root / OUTPUT_NAME).read_bytes())

    def test_scheduler_wires_recorder_to_existing_status_not_new_timer(self):
        src = (Path(__file__).resolve().parents[1] / "TABLET_SCHEDULED_UPDATE.sh").read_text(encoding="utf-8")
        self.assertIn("execution.tablet_autonomy_evidence_journal_v654", src)
        self.assertIn('--autonomy-result "$result"', src)
        self.assertIn("SCHEDULE_HOUR=\"23\"", src)
        self.assertNotIn("reset --hard", src)


if __name__ == "__main__":
    unittest.main()

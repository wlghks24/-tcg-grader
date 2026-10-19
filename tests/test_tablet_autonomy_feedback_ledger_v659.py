"""V659 SQLite transaction staging: synthetic only, never neural training."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from execution.tablet_autonomy_feedback_ledger_v659 import (
    Guarded, audit, stage_pairs,
)


def pair(ref="v374:confirmed:2026-10-01:2026-10-02", reward=0.9):
    skill = {"verified": True, "recipe": "RECOVER_SOURCE_HEALTH",
             "reward": reward, "evidence_ref": ref}
    meta = {"verified": True, "action_id": "RECHECK_DEGRADED_SOURCES",
            "reward": reward, "features": [0.3] * 10,
            "evidence_ref": "v375:" + ref}
    return skill, meta


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / "candidate-pairs.db"

    def test_no_db_read_is_nonmutating(self):
        self.assertEqual("NO_LEDGER", audit(self.db)["status"])
        self.assertFalse(self.db.exists())

    def test_pair_stages_without_promoting_confidence(self):
        result = stage_pairs(self.db, [pair()])
        self.assertEqual(1, result["staged"])
        self.assertFalse(result["training_authorized"])
        self.assertEqual(1, audit(self.db)["count"])
        self.assertFalse(audit(self.db)["independent_attestation"])

    def test_exact_replay_is_idempotent(self):
        stage_pairs(self.db, [pair()])
        self.assertEqual(0, stage_pairs(self.db, [pair()])["staged"])
        self.assertEqual(1, audit(self.db)["count"])

    def test_batch_rollback_on_conflicting_duplicate(self):
        stage_pairs(self.db, [pair()])
        new = pair(ref="v374:confirmed:2026-10-03:2026-10-04")
        conflicting = pair(reward=0.8)
        with self.assertRaises(Guarded):
            stage_pairs(self.db, [new, conflicting])
        self.assertEqual(1, audit(self.db)["count"])

    def test_action_mismatch_fails_without_creating_db(self):
        s, m = pair()
        m["action_id"] = "TRAIN_QUERY_STRATEGY"
        with self.assertRaises(Guarded):
            stage_pairs(self.db, [(s, m)])
        self.assertFalse(self.db.exists())

    def test_boolean_reward_is_rejected(self):
        s, m = pair()
        s["reward"] = True
        with self.assertRaises(Guarded):
            stage_pairs(self.db, [(s, m)])

    def test_missing_meta_features_is_rejected(self):
        s, m = pair()
        m["features"] = []
        with self.assertRaises(Guarded):
            stage_pairs(self.db, [(s, m)])

    def test_symlink_ledger_is_rejected(self):
        self.db.symlink_to(self.root / "missing")
        with self.assertRaises(Guarded):
            stage_pairs(self.db, [pair()])
        self.assertEqual("UNSAFE_LEDGER_HOLD", audit(self.db)["status"])

    def test_tampered_digest_refuses_trust(self):
        stage_pairs(self.db, [pair()])
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE candidate_pairs SET sha256='bad'")
        self.assertEqual("LEDGER_INTEGRITY_HOLD", audit(self.db)["status"])

    def test_cannot_mark_verified_in_ledger(self):
        stage_pairs(self.db, [pair()])
        with sqlite3.connect(self.db) as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE candidate_pairs SET status='VERIFIED'")
        self.assertEqual(1, audit(self.db)["count"])

    def test_total_capacity_cap_is_enforced_for_existing_rows(self):
        rows = [pair(ref=f"v374:run:{i}:2026-10-19") for i in range(256)]
        self.assertEqual(256, stage_pairs(self.db, rows)["staged"])
        with self.assertRaisesRegex(Guarded, "LEDGER_CAPACITY_HOLD"):
            stage_pairs(self.db, [pair(ref="v374:run:257:2026-10-19")])
        self.assertEqual(256, audit(self.db)["count"])

    def test_tampered_preexisting_entry_fails_closed_on_next_stage(self):
        stage_pairs(self.db, [pair()])
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE candidate_pairs SET sha256='tampered'")
        with self.assertRaisesRegex(Guarded, "EXISTING_LEDGER_TAMPERED"):
            stage_pairs(self.db, [pair(ref="v374:run:new:2026-10-19")])
        self.assertEqual("LEDGER_INTEGRITY_HOLD", audit(self.db)["status"])

    def test_legacy_training_jsonl_unmodified(self):
        old = self.root / "tablet_autonomy_verified_outcomes.jsonl"
        old.write_text('preserved\n')
        stage_pairs(self.db, [pair()])
        self.assertEqual("preserved\n", old.read_text())
        self.assertTrue(audit(self.db)["training_authorized"] is False)


if __name__ == "__main__":
    unittest.main()

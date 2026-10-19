"""Negative/positive V658 pre- and post-V400 feedback safety tests."""
import json
import tempfile
import unittest
from pathlib import Path
from execution.tablet_autonomy_feedback_preflight_v658 import inspect
from execution.tablet_autonomy_outcome_lineage_v657 import SKILLS, META

REF = "v374:source_health_improved:2026-10-01:2026-10-02"


def skill(reward=0.9):
    return {"verified": True, "recipe": "RECOVER_SOURCE_HEALTH",
            "skill_id": "trial-1", "reward": reward,
            "regression_detected": False, "evidence_ref": REF,
            "verified_at": "2026-10-02T00:00:00+00:00"}


def meta(ref=REF, reward=0.9):
    return {"verified": True, "action_id": "RECHECK_DEGRADED_SOURCES",
            "reward": reward, "features": [0.3] * 10, "evidence_ref": "v375:" + ref}


class FeedbackGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write(self, path, rows):
        (self.root / path).write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )

    def test_absent_both_only_allows_original_confidence_gate(self):
        r = inspect(self.root)
        self.assertEqual("COLD_START_SAFE_TO_EVALUATE_GATE", r["status"])
        self.assertTrue(r["allow_v400_attempt"])
        self.assertFalse(r["independent_attestation_confirmed"])
        self.assertEqual(0, r["training_outcomes_minted"])

    def test_empty_both_allowed_but_not_training_evidence(self):
        self.write(SKILLS, [])
        self.write(META, [])
        r = inspect(self.root)
        self.assertTrue(r["allow_v400_attempt"])
        self.assertFalse(r["independent_attestation_confirmed"])

    def test_partial_skill_write_blocks_before_training(self):
        self.write(SKILLS, [skill()])
        self.assertFalse(inspect(self.root)["allow_v400_attempt"])

    def test_partial_meta_write_blocks_before_training(self):
        self.write(META, [meta()])
        self.assertFalse(inspect(self.root)["allow_v400_attempt"])

    def test_both_matching_schemas_still_require_independent_attestation(self):
        self.write(SKILLS, [skill()])
        self.write(META, [meta()])
        r = inspect(self.root)
        self.assertEqual("FEEDBACK_PROVENANCE_HOLD", r["status"])
        self.assertEqual(1, r["details"]["schema_linked_pairs"])
        self.assertFalse(r["independent_attestation_confirmed"])

    def test_reward_drift_blocks(self):
        self.write(SKILLS, [skill()])
        self.write(META, [meta(reward=0.3)])
        self.assertIn("ACTION_OR_REWARD_MISMATCH", inspect(self.root)["details"]["issues"])

    def test_duplicate_ref_blocks(self):
        self.write(SKILLS, [skill(), skill()])
        self.write(META, [meta()])
        self.assertFalse(inspect(self.root)["allow_v400_attempt"])

    def test_symlink_blocks(self):
        (self.root / SKILLS).symlink_to(self.root / "missing")
        self.assertFalse(inspect(self.root)["allow_v400_attempt"])

    def test_corrupt_row_blocks(self):
        (self.root / META).write_text("{bad\n", encoding="utf-8")
        self.assertFalse(inspect(self.root)["allow_v400_attempt"])

    def test_unrelated_meta_origin_does_not_bypass(self):
        self.write(SKILLS, [])
        self.write(META, [{**meta(), "evidence_ref": "other:opaque"}])
        self.assertFalse(inspect(self.root)["allow_v400_attempt"])

    def test_read_only_repeated(self):
        self.write(SKILLS, [skill()])
        self.write(META, [meta()])
        old = {p.name: p.read_bytes() for p in self.root.iterdir()}
        self.assertEqual(inspect(self.root), inspect(self.root))
        self.assertEqual(old, {p.name: p.read_bytes() for p in self.root.iterdir()})

    def test_scheduler_preflight_precedes_v400_and_postflight_checks(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "TABLET_SCHEDULED_UPDATE.sh").read_text(encoding="utf-8")
        call = 'python -m execution.tablet_autonomy_feedback_preflight_v658 --root "$ROOT"'
        run = 'python tablet_autonomous_evolution_v400.py --domain tablet_gpt --execute-safe-learning'
        self.assertGreaterEqual(source.count(call), 2)
        self.assertLess(source.index(call), source.index(run))
        self.assertIn('write_autonomy_status "FEEDBACK_INTEGRITY_HOLD"', source)
        self.assertIn('return 14', source)
        self.assertIn('return 15', source)
        self.assertIn('return "$rc"', source)


if __name__ == "__main__":
    unittest.main()

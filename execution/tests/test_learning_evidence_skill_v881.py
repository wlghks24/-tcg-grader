"""TCG learning-evidence skill routing and real entry-path safety contracts.

Checks are deterministic and local: no external skills, network, devices or
project source mutation are invoked.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import grading_self_learning as learning

SKILL = ROOT / ".github/skills/tcg-learning-evidence-integrity/SKILL.md"
ROUTER = ROOT / ".github/skills/tcg-skill-router/SKILL.md"


class LearningEvidenceSkillV881Tests(unittest.TestCase):
    def test_skill_is_registered_and_covers_both_protected_p0_paths(self):
        skill = SKILL.read_text(encoding="utf-8")
        router = ROUTER.read_text(encoding="utf-8")
        self.assertIn("name: tcg-learning-evidence-integrity", skill)
        self.assertIn("tcg-learning-evidence-integrity", router)
        for token in (
            "confirmed_samples", "tcg_updater.py", "grading_self_learning.py",
            "sanitize_sample", "sanitize_legacy_rows", "_dedupe",
            "append_confirmed_sample", "bgs_empirical_summary",
            "V1–V100", "V101–V200", "HOLD", "SUCCESS",
        ):
            with self.subTest(token=token):
                # FAIL CLOSED: acceptance criteria must be traceable to source.
                if token == "SUCCESS":
                    self.assertIn("CI", skill)
                else:
                    self.assertIn(token, skill)

    def test_skill_requires_independent_actual_behavior_not_only_static(self):
        skill = SKILL.read_text(encoding="utf-8")
        for token in (
            "actual endpoint/disk regression", "two overlapping/concurrent requests",
            "backup corruption", "atomic-write failures", "exact candidate Git blob",
            "CodeQL", "Exhaustive SELFREFINE", "second reviewer",
            "physical Lenovo", "not a dependency",
        ):
            with self.subTest(token=token):
                self.assertIn(token, skill)

    def test_training_rejects_truthy_nonboolean_inputs_through_direct_paths(self):
        good = {"company": "PSA", "actual": 9, "pred": 10, "verified": True,
                "card_key": "skill-test-verified"}
        for bad in ("false", "true", 1, 0, None, False):
            with self.subTest(value=repr(bad)):
                row = {**good, "verified": bad}
                with self.assertRaises(ValueError):
                    learning.sanitize_sample(row)
                with self.assertRaises(ValueError):
                    learning.append_confirmed_sample(learning.empty_store(), row)
                self.assertEqual(0, learning.build_calibration([row])["PSA"]["n"])
        self.assertEqual(1, learning.build_calibration([good])["PSA"]["n"])

    def test_sparse_identity_round_trip_preserves_confirmation(self):
        original = {"company": "PSA", "actual": 9, "pred": 10,
                    "verified": True, "time": "2026-01-01T00:00:00+00:00"}
        first = learning.sanitize_sample(original)
        second = learning.sanitize_sample(first)
        self.assertEqual(learning._sample_identity(first),
                         learning._sample_identity(second))
        self.assertNotIn("card_key", first)
        rebuilt = learning.rebuild_store({"confirmed_samples": [original]})
        self.assertEqual(1, len(rebuilt["confirmed_samples"]))
        self.assertEqual(1, rebuilt["calibration"]["PSA"]["n"])


if __name__ == "__main__":
    unittest.main()

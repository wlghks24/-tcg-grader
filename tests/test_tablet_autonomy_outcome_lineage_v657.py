"""V657 negative/positive cross-store tests; fixtures are never training evidence."""
import json
import tempfile
import unittest
from pathlib import Path
from execution.tablet_autonomy_outcome_lineage_v657 import audit, SKILLS, META

REF = "v374:source_health_improved:2026-10-01:2026-10-02"


def skill(recipe="RECOVER_SOURCE_HEALTH", reward=0.9):
    return {"verified": True, "recipe": recipe, "skill_id": "A", "reward": reward,
            "regression_detected": False, "evidence_ref": REF, "verified_at": "2026-10-02T00:00:00+00:00"}


def meta(action="RECHECK_DEGRADED_SOURCES", reward=0.9, ref=REF):
    return {"verified": True, "action_id": action, "reward": reward,
            "features": [0.3] * 10, "evidence_ref": "v375:" + ref}


class LineageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def save(self, name, rows):
        (self.root / name).write_text("\n".join(json.dumps(x) for x in rows) + "\n", encoding="utf-8")

    def test_bare_bootstrap_is_not_training(self):
        x = audit(self.root)
        self.assertEqual("NO_VERIFIED_OUTCOME_FILES", x["status"])
        self.assertEqual(0, x["schema_linked_pairs"])
        self.assertFalse(x["training_authorized"])

    def test_genuine_schema_link_still_unattested(self):
        self.save(SKILLS, [skill()]); self.save(META, [meta()])
        x = audit(self.root)
        self.assertEqual("LINKED_SCHEMA_ONLY_NO_INDEPENDENT_ATTESTATION", x["status"])
        self.assertEqual(1, x["schema_linked_pairs"])
        self.assertFalse(x["independent_causal_attestation"])
        self.assertFalse(x["v387_confidence_changed"])

    def test_skill_without_meta_is_partial_feed(self):
        self.save(SKILLS, [skill()])
        self.assertEqual("PARTIAL_FEED_HOLD", audit(self.root)["status"])

    def test_orphan_meta_is_blocked(self):
        self.save(SKILLS, [skill()]); self.save(META, [meta(ref="unrelated")])
        self.assertIn("ORPHAN_META_OUTCOME", audit(self.root)["issues"])

    def test_action_mismatch_is_blocked(self):
        self.save(SKILLS, [skill()]); self.save(META, [meta(action="TRAIN_QUERY_STRATEGY")])
        self.assertIn("ACTION_OR_REWARD_MISMATCH", audit(self.root)["issues"])

    def test_other_meta_origin_is_not_falsely_declared_tampering(self):
        self.save(SKILLS, [skill(recipe="OBSERVE_ONLY")])
        self.save(META, [meta(ref="unrelated") | {"evidence_ref": "external:opaque"}])
        report = audit(self.root)
        self.assertEqual("NO_LINKABLE_RECORDS", report["status"])
        self.assertEqual(0, report["schema_linked_pairs"])
        self.assertFalse(report["independent_causal_attestation"])

    def test_reward_mismatch_is_blocked(self):
        self.save(SKILLS, [skill()]); self.save(META, [meta(reward=0.2)])
        self.assertIn("ACTION_OR_REWARD_MISMATCH", audit(self.root)["issues"])

    def test_duplicate_skill_ref_is_blocked(self):
        self.save(SKILLS, [skill(), skill()]); self.save(META, [meta()])
        self.assertIn("DUPLICATE_SKILL_EVIDENCE", audit(self.root)["issues"])

    def test_duplicate_meta_ref_is_blocked(self):
        self.save(SKILLS, [skill()]); self.save(META, [meta(), meta()])
        self.assertIn("DUPLICATE_META_EVIDENCE", audit(self.root)["issues"])

    def test_invalid_json_is_blocked(self):
        (self.root / SKILLS).write_text("{bad")
        self.save(META, [meta()])
        self.assertEqual("CORRUPTION_HOLD", audit(self.root)["status"])

    def test_symlink_is_blocked(self):
        (self.root / SKILLS).symlink_to(self.root / "missing")
        self.save(META, [meta()])
        self.assertEqual("CORRUPTION_HOLD", audit(self.root)["status"])

    def test_unverified_model_mapping_is_not_promoted(self):
        self.save(SKILLS, [skill(recipe="RECOVER_MODEL")]); self.save(META, [meta()])
        x = audit(self.root)
        self.assertIn("UNATTESTED_OR_UNKNOWN_ACTION_MAPPING", x["issues"])
        self.assertEqual(0, x["schema_linked_pairs"])

    def test_idempotent_no_file_write(self):
        self.save(SKILLS, [skill()]); self.save(META, [meta()])
        before = {p.name:p.read_bytes() for p in self.root.iterdir()}
        self.assertEqual(audit(self.root), audit(self.root))
        self.assertEqual(before, {p.name:p.read_bytes() for p in self.root.iterdir()})

    def test_nan_and_bool_values_cannot_be_trusted(self):
        self.save(SKILLS, [skill(reward=True)])
        self.save(META, [meta()])
        self.assertIn("INVALID_SKILL_SCHEMA", audit(self.root)["issues"])

    def test_scheduler_and_ci_run_passive_audit(self):
        root = Path(__file__).resolve().parents[1]
        shell = (root / "TABLET_SCHEDULED_UPDATE.sh").read_text(encoding="utf-8")
        flow = (root / ".github/workflows/android-updater-guard.yml").read_text(encoding="utf-8")
        self.assertIn("python -m execution.tablet_autonomy_outcome_lineage_v657", shell)
        self.assertIn("test_tablet_autonomy_outcome_lineage_v657.py", flow)
        self.assertIn('return "$rc"', shell)


if __name__ == "__main__":
    unittest.main()

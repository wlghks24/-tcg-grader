import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import tablet_autonomous_ai as ai

NOW = datetime(2026, 10, 1, 4, 0, tzinfo=timezone.utc)


def context(**signals):
    base = {name: 0.0 for name in ai.SIGNALS}
    base.update(signals)
    return {"observed_at": NOW.isoformat(), "signals": base, "market_fresh": True, "runtime_fresh": True, "evidence": [{"path": "fixture", "fresh": True}]}


class TabletAutonomousAIV371Tests(unittest.TestCase):
    def test_forbidden_autonomy_contract(self):
        self.assertTrue(all(value is False for value in ai.FORBIDDEN.values()))
        self.assertNotIn("WRITE_SOURCE", ai.AUTO_ACTIONS)
        self.assertNotIn("MERGE_MAIN", ai.AUTO_ACTIONS)

    def test_fresh_market_shift_can_select_verified_collection(self):
        result = ai.plan(context(market_shift=0.9, market_volatility=0.5), ai.default_state(), now=NOW)
        row = next(x for x in result["decisions"] if x["capability_id"] == "market_regime_adaptation")
        self.assertTrue(row["selected"])
        self.assertTrue(row["auto_execution_allowed"])

    def test_stale_market_holds_action(self):
        ctx = context(market_shift=0.9)
        ctx["market_fresh"] = False
        result = ai.plan(ctx, ai.default_state(), now=NOW)
        row = next(x for x in result["decisions"] if x["capability_id"] == "market_regime_adaptation")
        self.assertFalse(row["auto_execution_allowed"])
        self.assertIn("MARKET_EVIDENCE_NOT_FRESH", row["hold_reasons"])

    def test_unknown_conflict_blocks_ocr_and_grading_auto_promotion(self):
        result = ai.plan(context(ocr_gap=1, grading_gap=1, unknown=1, conflict=1), ai.default_state(), now=NOW)
        for capability in ("ocr_identity_recalibration", "grading_calibration"):
            row = next(x for x in result["decisions"] if x["capability_id"] == capability)
            self.assertTrue(row["selected"])
            self.assertFalse(row["auto_execution_allowed"])
            self.assertIn("UNKNOWN_CONFLICT_REQUIRES_VERIFIED_LABELS", row["hold_reasons"])

    def test_sync_stale_selects_fail_closed_recovery(self):
        result = ai.plan(context(sync_gap=1.0), ai.default_state(), now=NOW)
        row = next(x for x in result["decisions"] if x["capability_id"] == "tablet_sync_recovery")
        self.assertTrue(row["auto_execution_allowed"])
        self.assertEqual("SYNC_CHECK_AND_RECOVER", row["action"])

    def test_feature_gap_proposal_never_contains_source(self):
        result = ai.plan(context(unknown=1, conflict=0.8, ocr_gap=0.6), ai.default_state(), now=NOW)
        proposals = ai.build_proposals(result)
        self.assertTrue(proposals)
        self.assertTrue(all(x["source_code_generated"] is False for x in proposals))
        self.assertTrue(all(x["implementation_policy"] == "existing_verified_rule_or_branch_pr_only" for x in proposals))

    def test_unverified_outcome_is_rejected(self):
        state = ai.default_state()
        result = ai.record_verified_outcome(state, capability_id="market_regime_adaptation", context=context(), outcome=True, verification_level="targeted")
        self.assertFalse(result["accepted"])
        self.assertEqual([], state["labels"])

    def test_neural_inactive_without_verified_volume(self):
        model = ai.train_verified_policy([])
        self.assertFalse(model["active"])
        self.assertEqual("insufficient_verified_labels", model["reason"])

    def test_corrupt_primary_and_backup_hold_persistence(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            path.write_text("{broken", encoding="utf-8")
            Path(str(path) + ".bak").write_text("[]", encoding="utf-8")
            state, source, corruption = ai.load_state(path)
            self.assertTrue(corruption)
            self.assertEqual("corruption_hold", source)
            with self.assertRaises(ValueError):
                ai.save_state(state, path, corruption_hold=True)
            self.assertEqual("{broken", path.read_text(encoding="utf-8"))

    def test_action_cooldown_prevents_loop(self):
        state = ai.default_state()
        state["last_actions"]["market_regime_adaptation"] = NOW.isoformat()
        result = ai.plan(context(market_shift=1), state, now=NOW)
        row = next(x for x in result["decisions"] if x["capability_id"] == "market_regime_adaptation")
        self.assertFalse(row["auto_execution_allowed"])
        self.assertIn("ACTION_COOLDOWN_ACTIVE", row["hold_reasons"])

    def test_mark_action_rejects_non_auto_capability(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "state.json"
            with patch.object(ai, "STATE", path):
                result = ai.mark_action("feature_gap_expansion", state_path=path)
            self.assertFalse(result["ok"])


if __name__ == "__main__":
    unittest.main()

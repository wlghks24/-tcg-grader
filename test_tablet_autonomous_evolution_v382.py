import unittest
from datetime import datetime, timezone

import tablet_autonomous_evolution_v382 as v382

class TabletAutonomousEvolutionV382Tests(unittest.TestCase):
    def test_verified_reliability_quarantines_bad_action(self):
        base={"policy_evolution_v381":{
            "selection":{"champion_action":"TRAIN_QUERY_STRATEGY"},
            "verified_outcome_stats":{"TRAIN_QUERY_STRATEGY":{
                "verified_samples":16,"reward_mean":-0.6,"reward_min":-1.0
            }}
        }}
        r=v382.policy_reliability(base)
        self.assertTrue(r["quarantine_recommended"])
        self.assertLess(r["lower_confidence_bound"],-0.2)

    def test_neural_calibration_uses_verified_outcomes_only(self):
        base={"policy_evolution_v381":{"candidate_actions":[
            {"action_id":"TRAIN_QUERY_STRATEGY","verified_samples":16,"reward_mean":1.0,"neural_score":0.0},
            {"action_id":"TRAIN_JOB_STRATEGY","verified_samples":2,"reward_mean":-1.0,"neural_score":1.0},
        ]}}
        c=v382.neural_calibration(base)
        self.assertEqual(1,c["actions_compared"])
        self.assertTrue(c["hold_recommended"])
        self.assertFalse(c["model_weights_modified"])

    def test_high_drift_blocks_non_recovery(self):
        base={"autonomous_decision":{"allow_execution":True}}
        gate=v382.autonomous_gate(
            base,v382._default_state(),
            {"level":"HIGH","score":0.9},
            {"action_id":"TRAIN_QUERY_STRATEGY","quarantine_recommended":False},
            {"score":0.9},
            {"hold_recommended":False},
            now=datetime.now(timezone.utc),
        )
        self.assertFalse(gate["allow_execution"])
        self.assertEqual("V382_DRIFT_RECOVERY_ONLY",gate["status"])

    def test_high_drift_allows_recovery_when_upstream_allows(self):
        base={"autonomous_decision":{"allow_execution":True}}
        gate=v382.autonomous_gate(
            base,v382._default_state(),
            {"level":"HIGH","score":0.9},
            {"action_id":"REFRESH_MARKET_DATA","quarantine_recommended":False},
            {"score":0.9},
            {"hold_recommended":False},
            now=datetime.now(timezone.utc),
        )
        self.assertTrue(gate["allow_execution"])

    def test_feature_contracts_are_non_executable(self):
        base={"source_feature_proposals_v381":[{"id":"GAP:X","kind":"source_feature","reason":"persistent gap"}]}
        rows=v382.feature_contracts(base,{"level":"LOW","score":0.0},{"hold_recommended":False})
        self.assertTrue(rows)
        self.assertFalse(rows[0]["auto_execute"])
        self.assertFalse(rows[0]["auto_generate_source"])
        self.assertTrue(rows[0]["protected_pr_ci_required"])
        self.assertIn("actual_output_validation",rows[0]["acceptance_sequence"])

if __name__=="__main__":
    unittest.main(verbosity=2)

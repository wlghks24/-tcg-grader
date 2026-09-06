from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import ai_correlation_engine as corr
import ai_intelligence_pipeline as pipeline


class CorrelationTests(unittest.TestCase):
    def test_clusters_same_domain_and_cause(self):
        out = corr.correlate([
            {"incident_id":"a","domain":"tablet","severity":"high","message":"Termux boot startup failed","occurrences":2},
            {"incident_id":"b","domain":"tablet","severity":"medium","message":"Android reboot health check failed","occurrences":3},
        ])
        self.assertEqual(out["incident_count"], 2)
        self.assertGreaterEqual(out["cluster_count"], 1)
        self.assertTrue(any(c["domain"] == "tablet" for c in out["clusters"]))

    def test_contradiction_blocks_automatic_repair(self):
        out = corr.correlate([
            {"incident_id":"x","domain":"github","severity":"high","verified":True,"regression_pass":False,
             "message":"CI failed", "status":"open"}
        ])
        self.assertTrue(out["human_review_required"])
        self.assertTrue(out["contradictions"])
        self.assertEqual(out["recommended_test_plan"][0], "resolve contradictory evidence before auto-repair")

    def test_causal_chain_is_same_domain_only(self):
        out = corr.correlate([
            {"incident_id":"a","domain":"tablet","severity":"high","message":"origin/main mixed version deploy stale"},
            {"incident_id":"b","domain":"tablet","severity":"high","message":"Termux startup health check failed"},
            {"incident_id":"c","domain":"market","severity":"high","message":"429 rate limit collector"},
        ])
        self.assertTrue(any(x["domain"] == "tablet" for x in out["possible_causal_chains"]))
        self.assertFalse(any("market:" in x["possible_upstream"] and "tablet:" in x["possible_downstream"] for x in out["possible_causal_chains"]))

    def test_pipeline_uses_same_tracker_state(self):
        with tempfile.TemporaryDirectory() as td:
            state = Path(td) / "tracker.json"
            out = pipeline.run([
                {"domain":"tablet","severity":"high","stage":"BOOT","path":"START_TCG_UPDATER_ANDROID.sh",
                 "message":"Termux reboot startup health check failed", "evidence":"/api/v135-health unavailable"}
            ], state_path=state)
            self.assertTrue(state.exists())
            self.assertIn("intelligence", out)
            self.assertIn("intelligence", out["incidents"][0])
            self.assertTrue(out["intelligence"]["safety"]["same_tracker_state"])
            self.assertFalse(out["intelligence"]["safety"]["separate_learning_store"])

    def test_no_auto_patch_or_cross_domain_merge(self):
        out = corr.correlate([{"domain":"github","message":"syntax test failed"}])
        self.assertFalse(out["safety"]["auto_patch"])
        self.assertFalse(out["safety"]["cross_domain_state_merge"])
        self.assertFalse(out["safety"]["correlation_is_proof"])


if __name__ == "__main__":
    unittest.main()

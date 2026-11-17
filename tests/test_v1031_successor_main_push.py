"""V1031 main-push and full-gate regression; history stays immutable."""
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/v1025-full-coverage-successor.yml"


class V1031MainPushSuccessorTests(unittest.TestCase):
    def setUp(self):
        self.workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))

    def test_main_push_and_existing_events_are_all_enabled(self):
        events = self.workflow.get("on", self.workflow.get(True))
        self.assertEqual({"pull_request", "push", "workflow_dispatch"}, set(events))
        self.assertEqual({"branches": ["main"]}, events["push"])

    def test_full_gate_requires_all_shards_and_original_gates(self):
        jobs = self.workflow["jobs"]
        self.assertEqual(["root_regressions", "sync_generations"], jobs["full_gate"]["needs"])
        for key in ("root_regressions", "sync_generations"):
            self.assertEqual([i for i in range(16)], jobs[key]["strategy"]["matrix"]["shard"])
            self.assertIs(False, jobs[key]["strategy"]["fail-fast"])
        names = {step.get("name") for step in jobs["full_gate"]["steps"]}
        self.assertIn("Require every root and sync shard to pass", names)
        self.assertIn("Execute every original final gate script without bypass", names)

    def test_read_only_permissions_and_ref_scoped_concurrency(self):
        self.assertEqual({"contents": "read"}, self.workflow["permissions"])
        self.assertIn("${{ github.ref }}", self.workflow["concurrency"]["group"])
        self.assertIs(True, self.workflow["concurrency"]["cancel-in-progress"])
        self.assertNotIn("schedule", self.workflow.get("on", self.workflow.get(True)))

    def test_this_guard_and_existing_integrity_guards_still_execute(self):
        commands = "\n".join(step.get("run", "") for step in self.workflow["jobs"]["full_gate"]["steps"])
        self.assertIn("test_v1031_successor_main_push.py", commands)
        self.assertIn("test_v1026_legacy_browser_review.py", commands)
        self.assertIn("repository_integrity_guard.py", commands)


if __name__ == "__main__":
    unittest.main()

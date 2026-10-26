"""V680 independent historical CI proof and hostile-path/byte regression."""
import unittest
from pathlib import Path
from unittest.mock import patch

import sync_v376_successor_test_support as sync


class V680UIWorkflowLineageTests(unittest.TestCase):
    def test_existing_v641_proof_and_new_exact_ui_workflow(self):
        sync.assert_v641_autonomy_successor(self)
        sync.assert_v680_ui_workflow_successor(self)

    def test_historical_gate_delegates_only_after_new_and_prior_proofs_pass(self):
        watched = sorted(sync.V641_GAPS | {sync.V680_UI_WORKFLOW_PATH})
        sync._assert_successor_paths_reviewed(self, watched, [], generation="V426")
        sync._assert_successor_paths_reviewed(self, watched, [], generation="V427")

    def test_extra_unapproved_path_and_other_generations_remain_blocked(self):
        paths = sorted(sync.V641_GAPS | {sync.V680_UI_WORKFLOW_PATH, "unreviewed-extra-workflow.yml"})
        with self.assertRaises(AssertionError):
            sync._assert_successor_paths_reviewed(self, paths, [], generation="V426")
        with self.assertRaises(AssertionError):
            sync._assert_successor_paths_reviewed(self, [sync.V680_UI_WORKFLOW_PATH], [], generation="V500")

    def test_forged_successor_data_never_approves_changes(self):
        original = sync._read
        for key, value in (("reviewed_sha256", "0" * 64),
                           ("deployment_allowed", True),
                           ("candidate_commit", "0" * 40)):
            def forged(path):
                value_before = original(path)
                return {**value_before, key: value} if path == sync.V680_UI_PROOF_PATH else value_before
            with self.subTest(field=key), patch.object(sync, "_read", side_effect=forged):
                with self.assertRaises(AssertionError):
                    sync.assert_v680_ui_workflow_successor(self)

    def test_tampered_current_workflow_is_detected_after_original_pass(self):
        sync.assert_v680_ui_workflow_successor(self)
        read_original = Path.read_bytes
        target = sync.ROOT / sync.V680_UI_WORKFLOW_PATH
        def tampered(path):
            payload = read_original(path)
            return payload + b"\\n# changed without review" if path == target else payload
        with patch.object(Path, "read_bytes", tampered):
            with self.assertRaises(AssertionError):
                sync.assert_v680_ui_workflow_successor(self)


if __name__ == "__main__":
    unittest.main()

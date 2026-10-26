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

    def test_legacy_v369_and_v384_watched_routes_keep_original_scope(self):
        import test_tablet_gpt_tcg_grader_sync_v369 as v369
        import test_tablet_gpt_tcg_grader_sync_v384 as v384
        for legacy in (v369, v384):
            with self.subTest(name=legacy.__name__):
                contract = legacy.load(legacy.CONTRACT) if hasattr(legacy, "load") else legacy.read(legacy.CONTRACT)
                candidate = legacy.CANDIDATE_SHA if hasattr(legacy, "CANDIDATE_SHA") else legacy.CANDIDATE
                actual = legacy.watched_paths(contract, candidate)
                self.assertNotIn(sync.V680_UI_WORKFLOW_PATH, actual)
                self.assertTrue(actual)

    def test_unrelated_path_and_explicit_history_are_never_suppressed(self):
        path = sync.V680_UI_WORKFLOW_PATH
        other = "unreviewed-extra-path.py"
        self.assertEqual(sync.preserve_reviewed_v680_legacy_ui_scope(
            [path, other], "historical", head="old-tip"), [path, other])
        self.assertEqual(sync.preserve_reviewed_v680_legacy_ui_scope(
            [other], "historical"), [other])

    def test_changed_workflow_bytes_remain_visible_in_legacy_watcher(self):
        path = sync.V680_UI_WORKFLOW_PATH
        original = Path.read_bytes
        target = sync.ROOT / path
        def tampered(p):
            data = original(p)
            return data + b"unapproved change" if p == target else data
        import test_tablet_gpt_tcg_grader_sync_v369 as v369
        with patch.object(Path, "read_bytes", tampered):
            self.assertIn(path, sync.preserve_reviewed_v680_legacy_ui_scope(
                [path], v369.SOURCE))

    def test_review_does_not_hide_previous_path_mutations(self):
        path = sync.V680_UI_WORKFLOW_PATH
        original = sync.subprocess.run
        def different_history(command, *args, **kwargs):
            if (command[:3] == ["git", "diff", "--name-only"] and
                    command[-2:] == ["--", path]):
                return sync.subprocess.CompletedProcess(
                    command, 0, stdout=path + "\\n", stderr="")
            return original(command, *args, **kwargs)
        import test_tablet_gpt_tcg_grader_sync_v369 as v369
        with patch.object(sync.subprocess, "run", side_effect=different_history):
            self.assertIn(path, sync.preserve_reviewed_v680_legacy_ui_scope(
                [path], v369.SOURCE))

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

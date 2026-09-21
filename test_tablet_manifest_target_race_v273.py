#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

import tablet_gdrive_sync as core
import tablet_gdrive_sync_perf_v262 as perf


EXPECTED = "a" * 40
OLD = "b" * 40
OFFICIAL = "https://github.com/wlghks24/-tcg-grader.git"


class ManifestPinnedUpdateTests(unittest.TestCase):
    def test_runtime_passes_exact_manifest_sha_to_android_updater(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / ".git").mkdir()
            head_values = iter([OLD, EXPECTED])

            def fake_core_run(args, **kwargs):
                if args[:4] == ["git", "remote", "get-url", "origin"]:
                    return OFFICIAL
                if args[:3] == ["git", "rev-parse", "HEAD"]:
                    return next(head_values)
                self.fail(f"unexpected core.run call: {args}")

            completed = types.SimpleNamespace(returncode=0, stdout="ok")
            with mock.patch.object(perf.core, "run", side_effect=fake_core_run), \
                    mock.patch.object(perf.subprocess, "run", return_value=completed) as proc:
                perf.pinned_ensure_exact_main(repo, EXPECTED)

            self.assertEqual(1, proc.call_count)
            kwargs = proc.call_args.kwargs
            self.assertEqual("1", kwargs["env"]["TCG_UPDATE_ONLY"])
            self.assertEqual(EXPECTED, kwargs["env"]["TCG_TARGET_MAIN_SHA"])
            self.assertEqual(repo, kwargs["cwd"])
            self.assertEqual(["bash", "ANDROID_UPDATE_AND_START.sh"], proc.call_args.args[0])

    def test_already_exact_manifest_sha_does_not_launch_updater(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / ".git").mkdir()

            def fake_core_run(args, **kwargs):
                if args[:4] == ["git", "remote", "get-url", "origin"]:
                    return OFFICIAL
                if args[:3] == ["git", "rev-parse", "HEAD"]:
                    return EXPECTED
                self.fail(f"unexpected core.run call: {args}")

            with mock.patch.object(perf.core, "run", side_effect=fake_core_run), \
                    mock.patch.object(perf.subprocess, "run") as proc:
                perf.pinned_ensure_exact_main(repo, EXPECTED)
            proc.assert_not_called()

    def test_invalid_manifest_sha_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            (repo / ".git").mkdir()
            with mock.patch.object(perf.core, "run", return_value=OFFICIAL), \
                    self.assertRaisesRegex(ValueError, "invalid expected main sha"):
                perf.pinned_ensure_exact_main(repo, "not-a-sha")

    def test_runtime_patch_replaces_only_expected_main_resolver(self):
        original = core.ensure_exact_main
        try:
            perf.apply_runtime_patch()
            self.assertIs(core.ensure_exact_main, perf.pinned_ensure_exact_main)
        finally:
            core.ensure_exact_main = original

    def test_shell_updater_preserves_default_path_and_adds_pinned_path(self):
        src = Path("ANDROID_UPDATE_AND_START.sh").read_text(encoding="utf-8")
        required = (
            'TARGET_MAIN_SHA="${TCG_TARGET_MAIN_SHA:-}"',
            'git cat-file -e "${TARGET_MAIN_SHA}^{commit}"',
            'git merge-base --is-ancestor "$TARGET_MAIN_SHA" "$remote_head"',
            'git merge-base --is-ancestor "$local_head_candidate" "$TARGET_MAIN_SHA"',
            'verify_remote_candidate "$TARGET_MAIN_SHA"',
            'git merge --ff-only "$TARGET_MAIN_SHA"',
            'verify_remote_candidate "$remote_head"',
            'git merge --ff-only origin/main',
            'if [ "$final_exact_head" != "$TARGET_MAIN_SHA" ]',
        )
        for needle in required:
            self.assertIn(needle, src)
        self.assertNotIn("git reset --hard", src)
        self.assertLess(
            src.index('verify_remote_candidate "$TARGET_MAIN_SHA"'),
            src.index('git merge --ff-only "$TARGET_MAIN_SHA"'),
        )
        self.assertLess(
            src.index('verify_remote_candidate "$remote_head"'),
            src.index('git merge --ff-only origin/main'),
        )


if __name__ == "__main__":
    unittest.main()

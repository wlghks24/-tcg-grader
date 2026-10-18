#!/usr/bin/env python3
"""V644 exact-pinned purchase source successor, preserving V562 history."""
import hashlib
import subprocess
import tempfile
from pathlib import Path
from unittest import TestCase, main, mock

import sync_v376_successor_test_support as sync


class V644SuccessorTests(TestCase):
    def test_current_source_is_exact_v644_digest(self):
        source = sync.ROOT / sync.V562_PURCHASE_PATH
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                         sync.V644_PURCHASE_SHA256)

    def test_original_v562_candidate_still_pinned(self):
        original = subprocess.check_output(
            ["git", "show", f"{sync.V562_PURCHASE_CANDIDATE}:{sync.V562_PURCHASE_PATH}"],
            cwd=sync.ROOT,
        )
        self.assertEqual(hashlib.sha256(original).hexdigest(), sync.V562_PURCHASE_SHA256)

    def test_candidate_ancestor_and_byte_pins_fail_closed(self):
        watched = [sync.V562_PURCHASE_PATH, "other_unreviewed.py"]
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / sync.V562_PURCHASE_PATH
            source.write_bytes((sync.ROOT / sync.V562_PURCHASE_PATH).read_bytes())
            original = subprocess.check_output(
                ["git", "show", f"{sync.V562_PURCHASE_CANDIDATE}:{sync.V562_PURCHASE_PATH}"],
                cwd=sync.ROOT,
            )
            def git_check(cmd, *unused, **kwargs):
                if cmd[:2] == ["git", "show"]:
                    return original
                if cmd[:3] == ["git", "diff", "--name-only"] and "--" in cmd:
                    return [sync.V562_PURCHASE_PATH] if sync.V562_PURCHASE_CANDIDATE in cmd[3] else []
                raise AssertionError(cmd)
            with (mock.patch.object(sync, "ROOT", root),
                  mock.patch.object(sync.subprocess, "run", return_value=mock.Mock(returncode=0)),
                  mock.patch.object(sync.subprocess, "check_output", side_effect=git_check)):
                self.assertEqual(sync.preserve_reviewed_v644_purchase_scope(watched, "old-reviewed"),
                                 ["other_unreviewed.py"])
                self.assertEqual(sync.preserve_reviewed_v644_purchase_scope(watched, "old-reviewed", "base"),
                                 watched)
                source.write_bytes(b"future unreviewed edit")
                self.assertEqual(sync.preserve_reviewed_v644_purchase_scope(watched, "old-reviewed"),
                                 watched)

    def test_ancestry_failure_keeps_all_paths(self):
        watched = [sync.V562_PURCHASE_PATH]
        with mock.patch.object(sync.subprocess, "run", return_value=mock.Mock(returncode=1)):
            self.assertEqual(sync.preserve_reviewed_v644_purchase_scope(watched, "original"),
                             watched)


if __name__ == "__main__":
    main()

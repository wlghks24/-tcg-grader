#!/usr/bin/env python3
"""V563: exact reviewed CGC retry scope, immutable historical watch tests retained."""
from __future__ import annotations
import hashlib
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import sync_v376_successor_test_support as support


class ReviewedCgcScopeV563(unittest.TestCase):
    def test_pinned_source_and_reviewed_descendant_commit(self):
        source = support.ROOT / support.V563_CGC_PATH
        self.assertTrue(source.is_file())
        historical = subprocess.check_output(
            ["git", "show", f"{support.V563_CGC_CANDIDATE}:{support.V563_CGC_PATH}"],
            cwd=support.ROOT,
        )
        self.assertEqual(support.V563_CGC_SHA256,
                         hashlib.sha256(historical).hexdigest())
        self.assertEqual(support.V668_TAG_SHA256,
                         hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual("7711faecd9162c7780226237d4ef452edba190b1",
                         support.V668_TAG_CANDIDATE)
        self.assertEqual("fe36b5bdac06aacb4660d3419688da4ebaab98b0",
                         support.V563_CGC_CANDIDATE)
        self.assertEqual("c58e21f3a275562432656075bbfbc8aae378a0e2",
                         support.V563_CGC_BASE)

    def test_only_exact_confirmed_descendant_excludes_specific_path(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / support.V563_CGC_PATH
            path.write_bytes((support.ROOT / support.V563_CGC_PATH).read_bytes())
            visible = [support.V563_CGC_PATH, "grading_other_unreviewed.py"]
            with mock.patch.object(support, "ROOT", root), \
                 mock.patch.object(support.subprocess, "run",
                     return_value=mock.Mock(returncode=0)), \
                 mock.patch.object(support.subprocess, "check_output",
                     return_value=""):
                self.assertEqual(
                    ["grading_other_unreviewed.py"],
                    support.preserve_reviewed_v668_tag_scope(visible, "historic"),
                )
                self.assertEqual(
                    visible,
                    support.preserve_reviewed_v668_tag_scope(visible, "historic", "base"),
                )
                path.write_text("# changed after reviewed SHA", encoding="utf-8")
                self.assertEqual(
                    visible,
                    support.preserve_reviewed_v668_tag_scope(visible, "historic"),
                )

    def test_prior_unreviewed_change_or_nonancestor_never_hidden(self):
        visible = [support.V563_CGC_PATH]
        with mock.patch.object(support.subprocess, "run",
                               return_value=mock.Mock(returncode=1)):
            self.assertEqual(
                visible, support.preserve_reviewed_v668_tag_scope(visible, "historic")
            )
        with mock.patch.object(support.subprocess, "run",
                               return_value=mock.Mock(returncode=0)), \
             mock.patch.object(support.subprocess, "check_output",
                               return_value=support.V563_CGC_PATH + "\n"):
            self.assertEqual(
                visible, support.preserve_reviewed_v668_tag_scope(visible, "historic")
            )

    def test_historical_direct_helper_has_the_same_pinned_attribution(self):
        # V369-V384 import preserve_reviewed_v525_grade_scope directly.
        def identity(visible, *args, **kwargs):
            return visible

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            file = root / support.V563_CGC_PATH
            file.write_bytes((support.ROOT / support.V563_CGC_PATH).read_bytes())
            with (
                mock.patch.object(support, "ROOT", root),
                mock.patch.object(support, "preserve_reviewed_v545_static_scope", side_effect=identity),
                mock.patch.object(support, "preserve_reviewed_v546_publish_scope", side_effect=identity),
                mock.patch.object(support, "preserve_reviewed_v547_grading_scope", side_effect=identity),
                mock.patch.object(support.subprocess, "run", return_value=mock.Mock(returncode=0)),
                mock.patch.object(support.subprocess, "check_output", return_value=""),
            ):
                visible = [support.V563_CGC_PATH, "other_unreviewed.py"]
                self.assertEqual(
                    ["other_unreviewed.py"],
                    support.preserve_reviewed_v525_grade_scope(visible, "historic"),
                )
                self.assertEqual(
                    visible,
                    support.preserve_reviewed_v525_grade_scope(visible, "historic", "fixed_candidate"),
                )

    def test_new_successor_rejects_unreviewed_intervening_changes(self):
        visible = [support.V668_TAG_PATH, "unreviewed.py"]
        for outputs in ((support.V668_TAG_PATH + "\n", ""),
                        ("", support.V668_TAG_PATH + "\n")):
            with mock.patch.object(support.subprocess, "run",
                                   return_value=mock.Mock(returncode=0)), \
                 mock.patch.object(support.subprocess, "check_output",
                                   side_effect=outputs):
                self.assertEqual(visible,
                                 support.preserve_reviewed_v668_tag_scope(visible, "historic"))

    def test_new_successor_rejects_unreviewed_byte_change(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / support.V668_TAG_PATH).write_text("# unreviewed edit", encoding="utf-8")
            visible = [support.V668_TAG_PATH]
            with mock.patch.object(support, "ROOT", root), \
                 mock.patch.object(support.subprocess, "run",
                                   return_value=mock.Mock(returncode=0)):
                self.assertEqual(visible,
                                 support.preserve_reviewed_v668_tag_scope(visible, "historic"))

    def test_missing_or_unwatched_source_is_never_excluded(self):
        original = ["grading_other_unreviewed.py"]
        self.assertEqual(original,
                         support.preserve_reviewed_v563_cgc_scope(original, "historic"))


if __name__ == "__main__":
    unittest.main()

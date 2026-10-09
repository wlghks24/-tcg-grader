#!/usr/bin/env python3
"""V563: exact reviewed CGC retry scope, immutable historical watch tests retained."""
from __future__ import annotations
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import sync_v376_successor_test_support as support


class ReviewedCgcScopeV563(unittest.TestCase):
    def test_pinned_source_and_reviewed_descendant_commit(self):
        source = support.ROOT / support.V563_CGC_PATH
        self.assertTrue(source.is_file())
        self.assertEqual(support.V563_CGC_SHA256,
                         hashlib.sha256(source.read_bytes()).hexdigest())
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
                    support.preserve_reviewed_v563_cgc_scope(visible, "historic"),
                )
                self.assertEqual(
                    visible,
                    support.preserve_reviewed_v563_cgc_scope(visible, "historic", "base"),
                )
                path.write_text("# changed after reviewed SHA", encoding="utf-8")
                self.assertEqual(
                    visible,
                    support.preserve_reviewed_v563_cgc_scope(visible, "historic"),
                )

    def test_prior_unreviewed_change_or_nonancestor_never_hidden(self):
        visible = [support.V563_CGC_PATH]
        with mock.patch.object(support.subprocess, "run",
                               return_value=mock.Mock(returncode=1)):
            self.assertEqual(
                visible, support.preserve_reviewed_v563_cgc_scope(visible, "historic")
            )
        with mock.patch.object(support.subprocess, "run",
                               return_value=mock.Mock(returncode=0)), \
             mock.patch.object(support.subprocess, "check_output",
                               return_value=support.V563_CGC_PATH + "\n"):
            self.assertEqual(
                visible, support.preserve_reviewed_v563_cgc_scope(visible, "historic")
            )

    def test_missing_or_unwatched_source_is_never_excluded(self):
        original = ["grading_other_unreviewed.py"]
        self.assertEqual(original,
                         support.preserve_reviewed_v563_cgc_scope(original, "historic"))


if __name__ == "__main__":
    unittest.main()

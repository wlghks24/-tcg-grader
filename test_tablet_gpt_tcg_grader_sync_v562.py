#!/usr/bin/env python3
"""V562: a reviewed successor may not silence unreviewed sync changes."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import sync_v376_successor_test_support as support


class V562PurchaseSuccessor(unittest.TestCase):
    def test_real_candidate_hash_and_current_path(self):
        path = support.ROOT / support.V562_PURCHASE_PATH
        self.assertTrue(path.is_file())
        self.assertEqual(support.V562_PURCHASE_SHA256,
                         hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual("c346752ff00faaaa70fd40b04cd225f746c6b825",
                         support.V562_PURCHASE_BASE)
        self.assertEqual("a5674816058f23e2d92d8f781adaa4507606a079",
                         support.V562_PURCHASE_CANDIDATE)

    def test_only_exact_pinned_source_can_be_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = support.ROOT / support.V562_PURCHASE_PATH
            (root / support.V562_PURCHASE_PATH).write_bytes(source.read_bytes())
            watched = [support.V562_PURCHASE_PATH, "other_unreviewed.py"]
            with mock.patch.object(support, "ROOT", root), \
                 mock.patch.object(support.subprocess, "run",
                     return_value=mock.Mock(returncode=0)), \
                 mock.patch.object(support.subprocess, "check_output",
                     return_value=""):
                result = support.preserve_reviewed_v562_purchase_scope(watched, "old-generation")
                self.assertEqual(result, ["other_unreviewed.py"])
                self.assertEqual(watched, [support.V562_PURCHASE_PATH, "other_unreviewed.py"])
                self.assertEqual(
                    support.preserve_reviewed_v562_purchase_scope(watched, "old-generation", "base"),
                    watched,
                )
                (root / support.V562_PURCHASE_PATH).write_text("# altered", encoding="utf-8")
                self.assertEqual(
                    support.preserve_reviewed_v562_purchase_scope(watched, "old-generation"),
                    watched,
                )

    def test_older_changes_or_nonancestor_can_never_be_hidden(self):
        watched = [support.V562_PURCHASE_PATH]
        with mock.patch.object(support.subprocess, "run",
                               return_value=mock.Mock(returncode=1)):
            self.assertEqual(
                support.preserve_reviewed_v562_purchase_scope(watched, "historic"), watched
            )
        with mock.patch.object(support.subprocess, "run",
                               return_value=mock.Mock(returncode=0)), \
             mock.patch.object(support.subprocess, "check_output",
                               return_value=support.V562_PURCHASE_PATH + "\\n"):
            self.assertEqual(
                support.preserve_reviewed_v562_purchase_scope(watched, "historic"), watched
            )


if __name__ == "__main__":
    unittest.main()

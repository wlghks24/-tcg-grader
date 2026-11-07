"""V958 exact historical successor coverage; fixture-only read-only checks."""
import unittest
from pathlib import Path
from unittest.mock import patch

import sync_v376_successor_test_support as sync


class CatalogLineageV958Tests(unittest.TestCase):
    CATALOG = 'execution/tablet_catalog_bridge.py'
    REGRESSION = 'execution/tests/test_tablet_catalog_bridge.py'

    def test_v957_exact_candidate_preserves_v645_and_v653(self):
        sync.assert_v958_catalog_successor(self)
        # These historical contracts cannot be relaxed, replaced or skipped.
        sync.assert_v645_feature_successor(self)
        sync.assert_v653_successor(self)
        self.assertEqual(
            sync.V653_PROOF['reviewed_sha256'][self.CATALOG],
            sync.V958_CATALOG_PROOF['baseline_sha256'][self.CATALOG])
        self.assertEqual(
            sync.V645_FEATURE_PROOF['reviewed_sha256'][self.REGRESSION],
            sync.V958_CATALOG_PROOF['baseline_sha256'][self.REGRESSION])

    def test_direct_legacy_watches_preserve_prior_edits_and_non_head(self):
        later = sync.V653_PROOF['candidate_commit']
        paths = [self.CATALOG, self.REGRESSION]
        self.assertEqual([], sync.preserve_reviewed_v958_catalog_scope(paths, later))
        self.assertEqual([], sync.preserve_reviewed_v653_scope(paths, later))
        self.assertEqual([], sync.preserve_reviewed_v654_scope(paths, later))
        self.assertEqual([], sync.preserve_reviewed_v645_feature_scope(
            paths, sync.V645_FEATURE_PROOF['candidate_commit']))

        # A V645 pre-creation view must still see both old watched changes.
        before = sync.V645_FEATURE_PROOF['base_commit']
        self.assertEqual(paths, sync.preserve_reviewed_v958_catalog_scope(paths, before))
        candidate = sync.V958_CATALOG_PROOF['candidate_commit']
        self.assertEqual(paths, sync.preserve_reviewed_v958_catalog_scope(
            paths, later, head=candidate))

    def test_modified_current_source_cannot_be_hidden_after_cache_warmup(self):
        sync.assert_v958_catalog_successor(self)
        original = Path.read_bytes
        for path in (self.CATALOG, self.REGRESSION,
                     'execution/tablet_card_facts_v904.py',
                     'execution/tests/test_tablet_card_facts_v904.py',
                     '.github/workflows/v957-catalog-identity-offline.yml'):
            target = sync.ROOT / path

            def tamper(p):
                data = original(p)
                return data + b'\n# unreviewed' if p == target else data

            with self.subTest(path=path), patch.object(Path, 'read_bytes', tamper):
                with self.assertRaises(AssertionError):
                    sync.assert_v958_catalog_successor(self)
                self.assertEqual(
                    [path],
                    sync.preserve_reviewed_v958_catalog_scope(
                        [path], sync.V653_PROOF['candidate_commit']))

    def test_forged_review_deployment_and_changed_paths_rejected(self):
        original = sync._read
        receipt = sync.ROOT / '.github/tablet-autonomy/catalog_row_isolation_successor_v958.json'

        def forged(p):
            proof = original(p)
            if p == receipt:
                proof = dict(proof, deployment_allowed=True)
            return proof

        with patch.object(sync, '_read', side_effect=forged):
            with self.assertRaises(AssertionError):
                sync.assert_v958_catalog_successor(self)
            self.assertEqual(
                [self.CATALOG],
                sync.preserve_reviewed_v958_catalog_scope(
                    [self.CATALOG], sync.V653_PROOF['candidate_commit']))

        immutable = sync._v646_immutable_commit_evidence

        def unexpected(*args):
            ancestor, paths, rows = immutable(*args)
            return ancestor, paths | {'unreviewed.py'}, rows

        with patch.object(sync, '_v646_immutable_commit_evidence',
                          side_effect=unexpected):
            with self.assertRaises(AssertionError):
                sync.assert_v958_catalog_successor(self)


if __name__ == '__main__':
    unittest.main()

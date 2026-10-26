"""Preserve historical dependency pins and require complete CI partitions."""
import unittest
from pathlib import Path
from unittest.mock import patch
import sync_v376_successor_test_support as sync

class AlignmentPartitionTests(unittest.TestCase):
    def test_exact_new_evidence_preserves_historical_pin(self):
        sync.assert_v659_ci_successor(self)
        sync.assert_v647_ci_successor(self)
        self.assertEqual(sync.V647_CI_PROOF['reviewed_sha256'],sync.V659_CI_PROOF['baseline_sha256'])

    def test_current_bytes_are_checked_after_immutable_cache_warmup(self):
        sync.assert_v659_ci_successor(self)
        original=Path.read_bytes
        target=sync.ROOT/next(iter(sync.V659_CI_PROOF['reviewed_sha256']))
        with patch.object(Path,'read_bytes',lambda p:original(p)+b' unreviewed' if p==target else original(p)):
            with self.assertRaises(AssertionError):sync.assert_v659_ci_successor(self)
            with self.assertRaises(AssertionError):sync.assert_v647_ci_successor(self)

    def test_four_groups_cover_every_generation_without_overlap(self):
        files=sorted(sync.ROOT.glob('test_tablet_gpt_tcg_grader_sync_v*.py'),key=lambda p:int(p.stem.rsplit('v',1)[1]))
        groups=[files[i::4] for i in range(4)]
        self.assertTrue(all(groups));self.assertEqual(len(files),sum(map(len,groups)))
        self.assertEqual(set(files),{p for g in groups for p in g})
        source=(sync.ROOT/next(iter(sync.V659_CI_PROOF['reviewed_sha256']))).read_text()
        self.assertIn('shard: [0, 1, 2, 3]',source)
        self.assertIn('needs: sync-generations',source)
        self.assertIn('fail-fast: false',source)
        self.assertIn('python -m unittest -v "${tests[@]}"',source)
        # V672 explicitly verifies the reviewed follow-on workflow.
        sync.assert_v672_alignment_timeout_successor(self)
        self.assertEqual(1,source.count('timeout-minutes: 20'))
        self.assertEqual(1,source.count('timeout-minutes: 10'))
